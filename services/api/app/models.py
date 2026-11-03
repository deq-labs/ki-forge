"""SQLAlchemy models mirroring db/0001_initial.sql (the schema itself is owned by the migrations).

`tests/test_models.py` checks every table and column here against the migrated database.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    CHAR,
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, ENUM, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _enum(name: str, *values: str) -> ENUM:
    return ENUM(*values, name=name, create_type=False)


SessionKindEnum = _enum("session_kind", "lift", "conditioning")
EnrollmentStatusEnum = _enum("enrollment_status", "active", "paused", "completed", "abandoned")
TestTypeEnum = _enum(
    "test_type",
    "pullups_max",
    "pushups_max",
    "row_2k_seconds",
    "press_5rm_lb",
    "squat_5rm_lb",
    "deadlift_5rm_lb",
    "bodyweight_lb",
    "waist_in",
    "shoulders_in",
)
ScanStatusEnum = _enum("scan_status", "uploaded", "processing", "done", "failed")
SubStatusEnum = _enum("sub_status", "trialing", "active", "grace", "expired", "cancelled")
JobStatusEnum = _enum("job_status", "queued", "running", "done", "failed")

TZ = DateTime(timezone=True)
NOW = text("now()")
GEN_UUID = text("gen_random_uuid()")


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=GEN_UUID)


def _identity_pk(type_=SmallInteger) -> Mapped[int]:
    return mapped_column(type_, Identity(always=True), primary_key=True)


# --- users and accounts ----------------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    auth_id: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    units: Mapped[str] = mapped_column(Text, server_default="imperial")
    timezone: Mapped[str] = mapped_column(Text, server_default="America/New_York")
    keep_photos: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(TZ)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    push_token: Mapped[str] = mapped_column(Text, unique=True)
    platform: Mapped[str] = mapped_column(Text)
    last_seen: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)


class Subscription(Base):
    __tablename__ = "subscriptions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    provider: Mapped[str] = mapped_column(Text, server_default="revenuecat")
    entitlement: Mapped[str] = mapped_column(Text, server_default="pro")
    status: Mapped[str] = mapped_column(SubStatusEnum)
    store: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[dt.datetime | None] = mapped_column(TZ)
    updated_at: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)


# --- program content -------------------------------------------------------------------------------------


class PathRow(Base):
    __tablename__ = "paths"
    id: Mapped[int] = _identity_pk()
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    tagline: Mapped[str] = mapped_column(Text)
    build: Mapped[str] = mapped_column(Text)
    conditioning_exercise_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("exercises.id"))
    ratio_target: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    colors: Mapped[dict[str, Any]] = mapped_column(JSONB)
    emphasis: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_premium: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ExerciseRow(Base):
    __tablename__ = "exercises"
    id: Mapped[int] = _identity_pk()
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    equipment: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    needs_garage_space: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    swap_exercise_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("exercises.id"))
    increment_lb: Mapped[Decimal] = mapped_column(Numeric(4, 1), server_default="5")
    is_timed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ProgramRow(Base):
    __tablename__ = "programs"
    id: Mapped[int] = _identity_pk()
    slug: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    name: Mapped[str] = mapped_column(Text)


class PhaseRow(Base):
    __tablename__ = "phases"
    id: Mapped[int] = _identity_pk()
    program_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("programs.id"))
    ord: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(Text)
    display_name_template: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    start_week: Mapped[int] = mapped_column(SmallInteger)
    end_week: Mapped[int] = mapped_column(SmallInteger)
    rir_target: Mapped[int | None] = mapped_column(SmallInteger)
    deload_every: Mapped[int | None] = mapped_column(SmallInteger)
    calorie_mode: Mapped[str] = mapped_column(Text)
    modifiers: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")


class SessionTemplateRow(Base):
    __tablename__ = "session_templates"
    id: Mapped[int] = _identity_pk()
    program_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("programs.id"))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str] = mapped_column(Text)
    required_for_full_week: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    kind: Mapped[str] = mapped_column(SessionKindEnum)
    day_of_week: Mapped[int] = mapped_column(SmallInteger)
    gets_path_techniques: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    uses_path_conditioning: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class PrescriptionRow(Base):
    __tablename__ = "prescriptions"
    id: Mapped[int] = _identity_pk(Integer)
    session_template_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("session_templates.id", ondelete="CASCADE")
    )
    exercise_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("exercises.id"))
    ord: Mapped[int] = mapped_column(SmallInteger)
    sets: Mapped[int] = mapped_column(SmallInteger)
    rep_min: Mapped[int] = mapped_column(SmallInteger)
    rep_max: Mapped[int] = mapped_column(SmallInteger)
    rest_seconds: Mapped[int] = mapped_column(SmallInteger, server_default="90")
    superset_group: Mapped[str | None] = mapped_column(CHAR(1))
    is_main_lift: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    note: Mapped[str | None] = mapped_column(Text)


class PathTechniqueRow(Base):
    __tablename__ = "path_techniques"
    path_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("paths.id", ondelete="CASCADE"), primary_key=True
    )
    exercise_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("exercises.id"), primary_key=True)
    ord: Mapped[int] = mapped_column(SmallInteger)
    sets: Mapped[int] = mapped_column(SmallInteger)
    rep_min: Mapped[int] = mapped_column(SmallInteger)
    rep_max: Mapped[int] = mapped_column(SmallInteger)
    note: Mapped[str | None] = mapped_column(Text)


# --- a user's run ----------------------------------------------------------------------------------------


class Enrollment(Base):
    __tablename__ = "enrollments"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    program_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("programs.id"))
    path_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("paths.id"))
    cycle: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    current_phase_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("phases.id"))
    phase_started_on: Mapped[dt.date | None] = mapped_column(Date)
    started_on: Mapped[dt.date] = mapped_column(Date, server_default=text("current_date"))
    status: Mapped[str] = mapped_column(EnrollmentStatusEnum, server_default="active")
    garage_mode_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"))
    session_template_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("session_templates.id"))
    phase_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("phases.id"))
    week: Mapped[int] = mapped_column(SmallInteger)
    garage_mode: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    started_at: Mapped[dt.datetime] = mapped_column(TZ)
    completed_at: Mapped[dt.datetime | None] = mapped_column(TZ)


class SetLog(Base):
    __tablename__ = "set_logs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    workout_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE")
    )
    exercise_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("exercises.id"))
    set_no: Mapped[int] = mapped_column(SmallInteger)
    weight_lb: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="0")
    reps: Mapped[int | None] = mapped_column(SmallInteger)
    seconds: Mapped[int | None] = mapped_column(SmallInteger)
    rir: Mapped[int | None] = mapped_column(SmallInteger)
    is_swap: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("set_logs.id"))
    logged_at: Mapped[dt.datetime] = mapped_column(TZ)


class ProgressionStateRow(Base):
    __tablename__ = "progression_state"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    exercise_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("exercises.id"), primary_key=True)
    next_weight_lb: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    stall_count: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    updated_at: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)


# --- tests and scans -------------------------------------------------------------------------------------


class TestResult(Base):
    __tablename__ = "test_results"
    __test__ = False  # not a pytest test class
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    enrollment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("enrollments.id", ondelete="SET NULL"))
    phase_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("phases.id"))
    test: Mapped[str] = mapped_column(TestTypeEnum)
    value: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    taken_at: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)


class BodyScan(Base):
    __tablename__ = "body_scans"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(ScanStatusEnum, server_default="uploaded")
    photo_key: Mapped[str | None] = mapped_column(Text)
    shoulders_in: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    waist_in: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    tape_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3),
        Computed("CASE WHEN waist_in > 0 THEN round(shoulders_in / waist_in, 3) END", persisted=True),
    )
    est_ratio: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    landmarks: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    photo_delete_at: Mapped[dt.datetime | None] = mapped_column(TZ)
    taken_at: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)


# --- XP, levels, badges ----------------------------------------------------------------------------------


class XpEvent(Base):
    __tablename__ = "xp_events"
    id: Mapped[int] = _identity_pk(BigInteger)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(Text)
    amount: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)


class UserStats(Base):
    __tablename__ = "user_stats"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    total_xp: Mapped[int] = mapped_column(Integer, server_default="0")
    level: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    power_level: Mapped[int] = mapped_column(Integer, server_default="0")
    current_week_streak: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    updated_at: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)


class BadgeRow(Base):
    __tablename__ = "badges"
    id: Mapped[int] = _identity_pk()
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    xp_reward: Mapped[int] = mapped_column(Integer, server_default="75")
    rule: Mapped[dict[str, Any]] = mapped_column(JSONB)


class UserBadge(Base):
    __tablename__ = "user_badges"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    badge_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("badges.id"), primary_key=True)
    earned_at: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = _identity_pk(BigInteger)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    status: Mapped[str] = mapped_column(JobStatusEnum, server_default="queued")
    run_at: Mapped[dt.datetime] = mapped_column(TZ, server_default=NOW)
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[dt.datetime | None] = mapped_column(TZ)
