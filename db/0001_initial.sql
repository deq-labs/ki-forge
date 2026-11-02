-- Ki Forge Fitness — initial schema (PostgreSQL 18)
-- Migration 0001. Program content (paths, phases, templates) is data, so new
-- character paths and rep schemes ship as data migrations, not app releases.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;     -- case-insensitive email

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
CREATE TYPE session_kind      AS ENUM ('lift', 'conditioning');
CREATE TYPE enrollment_status AS ENUM ('active', 'paused', 'completed', 'abandoned');
CREATE TYPE test_type         AS ENUM ('pullups_max', 'pushups_max', 'row_2k_seconds',
                                       'press_5rm_lb', 'squat_5rm_lb', 'deadlift_5rm_lb',
                                       'bodyweight_lb', 'waist_in', 'shoulders_in');
CREATE TYPE scan_status       AS ENUM ('uploaded', 'processing', 'done', 'failed');
CREATE TYPE sub_status        AS ENUM ('trialing', 'active', 'grace', 'expired', 'cancelled');
CREATE TYPE job_status        AS ENUM ('queued', 'running', 'done', 'failed');

-- ---------------------------------------------------------------------------
-- Users and accounts
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_id       text   NOT NULL UNIQUE,          -- Clerk user id
    email         citext UNIQUE,
    display_name  text   NOT NULL,
    units         text   NOT NULL DEFAULT 'imperial' CHECK (units IN ('imperial', 'metric')),
    timezone      text   NOT NULL DEFAULT 'America/New_York',
    keep_photos   boolean NOT NULL DEFAULT false,   -- opt-in photo retention
    created_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz                        -- set during async deletion, row purged after
);

CREATE TABLE devices (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    push_token  text NOT NULL UNIQUE,                -- Expo push token
    platform    text NOT NULL CHECK (platform IN ('ios', 'android', 'web')),
    last_seen   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE subscriptions (
    user_id        uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    provider       text NOT NULL DEFAULT 'revenuecat',
    entitlement    text NOT NULL DEFAULT 'pro',
    status         sub_status NOT NULL,
    store          text CHECK (store IN ('app_store', 'play_store', 'stripe')),
    expires_at     timestamptz,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Program content (seeded, versioned)
-- ---------------------------------------------------------------------------
CREATE TABLE paths (
    id            smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    slug          text NOT NULL UNIQUE,              -- storm, shadow, titan, blade
    name          text NOT NULL,
    tagline       text NOT NULL,
    build         text NOT NULL,
    conditioning_exercise_id smallint,               -- FK added after exercises exists
    ratio_target  numeric(3,2) NOT NULL CHECK (ratio_target BETWEEN 1.0 AND 2.0),
    colors        jsonb NOT NULL,                    -- {"primary":"#ff7a1a","secondary":"#ffd23f"}
    emphasis      jsonb NOT NULL,                    -- {"delts":95,"back":85,...}
    is_premium    boolean NOT NULL DEFAULT false
);

CREATE TABLE exercises (
    id                smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    slug              text NOT NULL UNIQUE,
    name              text NOT NULL,
    equipment         text[] NOT NULL DEFAULT '{}',  -- {barbell,rack}
    needs_garage_space boolean NOT NULL DEFAULT false,
    swap_exercise_id  smallint REFERENCES exercises(id),  -- garage-mode substitute
    increment_lb      numeric(4,1) NOT NULL DEFAULT 5,
    is_timed          boolean NOT NULL DEFAULT false   -- timed/done work is logged as reps = 1
);
ALTER TABLE paths ADD CONSTRAINT paths_conditioning_fk FOREIGN KEY (conditioning_exercise_id) REFERENCES exercises(id);

CREATE TABLE programs (
    id        smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    slug      text NOT NULL,
    version   smallint NOT NULL DEFAULT 1,
    name      text NOT NULL,
    UNIQUE (slug, version)
);

CREATE TABLE phases (
    id              smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    program_id      smallint NOT NULL REFERENCES programs(id),
    ord             smallint NOT NULL,
    name            text NOT NULL,                  -- Trial 0, Foundation, Trial I, Build, ... Final Trial
    display_name_template text,                     -- e.g. '{path} Specialization'
    kind            text NOT NULL CHECK (kind IN ('phase', 'trial')),
    start_week      smallint NOT NULL CHECK (start_week >= 0),  -- week 0 = Trial 0 (test week)
    end_week        smallint NOT NULL,
    rir_target      smallint CHECK (rir_target BETWEEN 0 AND 4),  -- null for trials
    deload_every    smallint,                       -- every Nth week
    calorie_mode    text NOT NULL CHECK (calorie_mode IN ('maintenance', 'surplus', 'deficit')),
    modifiers       jsonb NOT NULL DEFAULT '{}',     -- main_lift_scheme, extra_sets, optional_day, ... (see docs/03-program-rules.md)
    CHECK (end_week >= start_week),
    UNIQUE (program_id, ord)
);

CREATE TABLE session_templates (
    id           smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    program_id   smallint NOT NULL REFERENCES programs(id),
    code         text NOT NULL,                     -- upper_a, lower_a, engine, upper_b, lower_b, easy_cardio
    name         text NOT NULL,
    short_name   text NOT NULL,
    required_for_full_week boolean NOT NULL DEFAULT true,
    kind         session_kind NOT NULL,
    day_of_week  smallint NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),  -- ISO, 1 = Monday
    gets_path_techniques boolean NOT NULL DEFAULT false,
    uses_path_conditioning boolean NOT NULL DEFAULT false,  -- template's PATH_CONDITIONING slot is filled from paths.conditioning_exercise_id
    UNIQUE (program_id, code)
);

CREATE TABLE prescriptions (
    id                   integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    session_template_id  smallint NOT NULL REFERENCES session_templates(id) ON DELETE CASCADE,
    exercise_id          smallint NOT NULL REFERENCES exercises(id),
    ord                  smallint NOT NULL,
    sets                 smallint NOT NULL CHECK (sets > 0),
    rep_min              smallint NOT NULL,
    rep_max              smallint NOT NULL,
    rest_seconds         smallint NOT NULL DEFAULT 90,
    superset_group       char(1),                   -- 'A' pairs with the next 'A'
    is_main_lift         boolean NOT NULL DEFAULT false,
    note                 text,
    CHECK (rep_max >= rep_min),
    UNIQUE (session_template_id, ord)
);

CREATE TABLE path_techniques (
    path_id              smallint NOT NULL REFERENCES paths(id) ON DELETE CASCADE,
    exercise_id          smallint NOT NULL REFERENCES exercises(id),
    ord                  smallint NOT NULL,
    sets                 smallint NOT NULL,
    rep_min              smallint NOT NULL,
    rep_max              smallint NOT NULL,
    note                 text,
    PRIMARY KEY (path_id, exercise_id)
);

-- ---------------------------------------------------------------------------
-- A user's run through the program
-- ---------------------------------------------------------------------------
CREATE TABLE enrollments (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    program_id        smallint NOT NULL REFERENCES programs(id),
    path_id           smallint NOT NULL REFERENCES paths(id),
    cycle             smallint NOT NULL DEFAULT 1,
    current_phase_id  smallint REFERENCES phases(id),
    phase_started_on  date,
    started_on        date NOT NULL DEFAULT current_date,
    status            enrollment_status NOT NULL DEFAULT 'active',
    garage_mode_default boolean NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX one_active_enrollment ON enrollments(user_id) WHERE status = 'active';

CREATE TABLE workout_sessions (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id            uuid NOT NULL UNIQUE,      -- generated on device; idempotent sync
    user_id              uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    enrollment_id        uuid NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    session_template_id  smallint NOT NULL REFERENCES session_templates(id),
    phase_id             smallint NOT NULL REFERENCES phases(id),
    week                 smallint NOT NULL CHECK (week >= 0),  -- program week the session was scheduled in
    garage_mode          boolean NOT NULL DEFAULT false,
    started_at           timestamptz NOT NULL,
    completed_at         timestamptz
);
CREATE INDEX workout_sessions_user_time ON workout_sessions(user_id, started_at DESC);
CREATE INDEX workout_sessions_enrollment_week ON workout_sessions(enrollment_id, week);

CREATE TABLE set_logs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           uuid NOT NULL UNIQUE,
    workout_session_id  uuid NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
    exercise_id         smallint NOT NULL REFERENCES exercises(id),
    set_no              smallint NOT NULL,
    weight_lb           numeric(6,2) NOT NULL DEFAULT 0,
    reps                smallint,
    seconds             smallint,                    -- timed work: rows, holds, carries
    rir                 smallint CHECK (rir BETWEEN 0 AND 5),
    is_swap             boolean NOT NULL DEFAULT false,
    supersedes_id       uuid REFERENCES set_logs(id),  -- append-only edits
    logged_at           timestamptz NOT NULL
);
CREATE INDEX set_logs_session ON set_logs(workout_session_id);
CREATE INDEX set_logs_exercise ON set_logs(exercise_id, logged_at DESC);

CREATE TABLE progression_state (
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_id   smallint NOT NULL REFERENCES exercises(id),
    next_weight_lb numeric(6,2) NOT NULL,
    stall_count   smallint NOT NULL DEFAULT 0,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, exercise_id)
);

-- ---------------------------------------------------------------------------
-- Tests and body scans
-- ---------------------------------------------------------------------------
CREATE TABLE test_results (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    enrollment_id  uuid REFERENCES enrollments(id) ON DELETE SET NULL,
    phase_id       smallint REFERENCES phases(id),   -- the Trial this closes
    test           test_type NOT NULL,
    value          numeric(7,2) NOT NULL,
    taken_at       timestamptz NOT NULL DEFAULT now(),
    -- one value per test per Trial per run, so PUT /v1/trials/{ord} can upsert.
    -- NULLs stay distinct so rows orphaned by ON DELETE SET NULL never collide.
    UNIQUE (user_id, enrollment_id, phase_id, test)
);
CREATE INDEX test_results_user ON test_results(user_id, test, taken_at DESC);

CREATE TABLE body_scans (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          scan_status NOT NULL DEFAULT 'uploaded',
    photo_key       text,                           -- R2 object key; null once deleted
    shoulders_in    numeric(4,1),                   -- tape
    waist_in        numeric(4,1),
    tape_ratio      numeric(4,3) GENERATED ALWAYS AS
                      (CASE WHEN waist_in > 0 THEN round(shoulders_in / waist_in, 3) END) STORED,
    est_ratio       numeric(4,3),                   -- from pose landmarks
    landmarks       jsonb,                          -- normalized 2D points, no image data
    photo_delete_at timestamptz,                    -- purge job target
    taken_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX body_scans_user ON body_scans(user_id, taken_at DESC);

-- ---------------------------------------------------------------------------
-- XP, levels, badges
-- ---------------------------------------------------------------------------
CREATE TABLE xp_events (
    id           bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type         text NOT NULL,                     -- set_logged, session_cleared, all_on_target,
                                                    -- full_week, deload_done, trial_passed, scan_logged, badge
    amount       integer NOT NULL CHECK (amount > 0),
    source_id    text NOT NULL,                     -- set client_id, session id, ISO week, badge slug
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, type, source_id)               -- every award is idempotent
);

CREATE TABLE user_stats (                           -- cache; rebuildable from xp_events + test_results
    user_id              uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    total_xp             integer NOT NULL DEFAULT 0,
    level                smallint NOT NULL DEFAULT 1,
    power_level          integer NOT NULL DEFAULT 0,
    current_week_streak  smallint NOT NULL DEFAULT 0,
    updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE badges (
    id          smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    slug        text NOT NULL UNIQUE,
    name        text NOT NULL,
    description text NOT NULL,
    xp_reward   integer NOT NULL DEFAULT 75,
    rule        jsonb NOT NULL                      -- {"metric":"sessions","gte":1}
);

CREATE TABLE user_badges (
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge_id   smallint NOT NULL REFERENCES badges(id),
    earned_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, badge_id)
);

-- Everyone starts at level 1; level k+1 is reached at 50*k^2 + 350*k total XP.
CREATE FUNCTION level_for_xp(xp integer) RETURNS smallint
LANGUAGE sql IMMUTABLE AS $$
    SELECT (floor((-350 + sqrt(350.0 * 350 + 200.0 * xp)) / 100) + 1)::smallint
$$;

-- ---------------------------------------------------------------------------
-- Background jobs (Postgres-backed queue; worker uses FOR UPDATE SKIP LOCKED)
-- ---------------------------------------------------------------------------
CREATE TABLE jobs (
    id          bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    kind        text NOT NULL,                      -- analyze_scan, run_progression, purge_photo, delete_user
    payload     jsonb NOT NULL DEFAULT '{}',
    status      job_status NOT NULL DEFAULT 'queued',
    run_at      timestamptz NOT NULL DEFAULT now(),
    attempts    smallint NOT NULL DEFAULT 0,
    last_error  text,
    locked_at   timestamptz
);
CREATE INDEX jobs_ready ON jobs(run_at) WHERE status = 'queued';

COMMIT;
