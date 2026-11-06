"""POST /v1/sync: the offline write path (docs/02-architecture.md, "Offline write path and sync").

In one transaction: upsert sessions and sets on their client ids (sets are append-only; an edit is a new
row superseding an older one), score every touched session with the rules engine, record XP awards
(idempotent), full-week bonuses and badges, refresh the stats cache and queue progression.
Replaying a batch changes nothing and awards nothing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.models import Enrollment, Job, SetLog, User, WorkoutSession
from app.rules.calendar import phase_for
from app.rules.completion import SessionScore, is_full_week
from app.rules.program import Badge, Program
from app.rules.xp import Award, full_week_award, session_awards
from app.services.awards import award_badges, record_awards
from app.services.program import program_ids
from app.services.sessions import score_stored
from app.services.stats import Stats, compute_stats, refresh_stats


@dataclass(frozen=True)
class SessionInput:
    client_id: uuid.UUID
    template_code: str
    week: int
    garage_mode: bool
    started_at: dt.datetime
    completed_at: dt.datetime | None = None


@dataclass(frozen=True)
class SetInput:
    client_id: uuid.UUID
    session_client_id: uuid.UUID
    exercise_slug: str
    set_no: int
    weight_lb: float
    logged_at: dt.datetime
    reps: int | None = None
    seconds: int | None = None
    rir: int | None = None
    is_swap: bool = False
    supersedes_client_id: uuid.UUID | None = None


@dataclass(frozen=True)
class SessionResult:
    client_id: uuid.UUID
    cleared: bool
    all_on_target: bool
    xp: int


@dataclass
class SyncResult:
    accepted_sessions: list[uuid.UUID] = field(default_factory=list)
    accepted_sets: list[uuid.UUID] = field(default_factory=list)
    xp_awarded: list[Award] = field(default_factory=list)
    stats: Stats | None = None
    level_before: int = 1
    new_badges: list[Badge] = field(default_factory=list)
    sessions: list[SessionResult] = field(default_factory=list)


def _reject(code: str, message: str) -> ApiError:
    return ApiError(422, code, message)


def _upsert_sessions(
    db: Session, user: User, e: Enrollment, program: Program, sessions: list[SessionInput]
) -> dict[uuid.UUID, WorkoutSession]:
    ids = program_ids(db)
    program = program.for_path(ids.path_slug(e.path_id))  # the run's program (a path may bring its own)
    codes = {t.code for t in program.session_templates if not t.garage_only}
    for s in sessions:
        if s.template_code not in ids.templates or s.template_code not in codes:
            raise _reject("unknown_template", f"session {s.client_id}: unknown template {s.template_code!r}")
        phase = phase_for(s.week, program)
        if phase is None or phase.is_trial:
            raise _reject("invalid_week", f"session {s.client_id}: week {s.week} has no training sessions")
        db.execute(
            insert(WorkoutSession)
            .values(
                client_id=s.client_id,
                user_id=user.id,
                enrollment_id=e.id,
                session_template_id=ids.templates[s.template_code],
                phase_id=ids.phase_id(program, phase.ord),
                path_id=e.path_id,
                week=s.week,
                garage_mode=s.garage_mode,
                started_at=s.started_at,
                completed_at=s.completed_at,
            )
            .on_conflict_do_nothing(index_elements=[WorkoutSession.client_id])
        )
        if s.completed_at is not None:
            db.execute(
                WorkoutSession.__table__.update()
                .where(
                    WorkoutSession.client_id == s.client_id,
                    WorkoutSession.user_id == user.id,
                    WorkoutSession.completed_at.is_(None),
                )
                .values(completed_at=s.completed_at)
            )
    wanted = {s.client_id for s in sessions}
    rows = {
        ws.client_id: ws
        for ws in db.scalars(select(WorkoutSession).where(WorkoutSession.client_id.in_(wanted)))
    }
    for cid in wanted:
        if rows[cid].user_id != user.id:
            raise ApiError(409, "client_id_conflict", f"session {cid} belongs to someone else")
    return rows


def _insert_sets(
    db: Session, user: User, sets: list[SetInput], batch_sessions: dict[uuid.UUID, WorkoutSession]
) -> set[uuid.UUID]:
    """Insert sets (ON CONFLICT DO NOTHING). Returns the workout session ids they belong to."""
    ids = program_ids(db)
    need = {s.session_client_id for s in sets} - set(batch_sessions)
    sessions = dict(batch_sessions)
    if need:
        sessions.update(
            {
                ws.client_id: ws
                for ws in db.scalars(select(WorkoutSession).where(WorkoutSession.client_id.in_(need)))
            }
        )
    for s in sets:
        ws = sessions.get(s.session_client_id)
        if ws is None or ws.user_id != user.id:
            raise _reject("unknown_session", f"set {s.client_id}: unknown session {s.session_client_id}")
        if s.exercise_slug not in ids.exercises:
            raise _reject("unknown_exercise", f"set {s.client_id}: unknown exercise {s.exercise_slug!r}")

    # Existing rows for every client id we may need to resolve (the sets themselves and what they supersede).
    lookup = {s.client_id for s in sets} | {s.supersedes_client_id for s in sets if s.supersedes_client_id}
    known: dict[uuid.UUID, SetLog] = {
        r.client_id: r for r in db.scalars(select(SetLog).where(SetLog.client_id.in_(lookup)))
    }
    owner = {ws.id: ws.user_id for ws in sessions.values()}
    for cid, row in known.items():
        if cid in {s.client_id for s in sets} and owner.get(row.workout_session_id, user.id) != user.id:
            raise ApiError(409, "client_id_conflict", f"set {cid} belongs to someone else")

    pending = [s for s in sets if s.client_id not in known]
    while pending:
        progressed = False
        for s in list(pending):
            prev = known.get(s.supersedes_client_id) if s.supersedes_client_id else None
            if s.supersedes_client_id and prev is None:
                continue  # wait until the row it supersedes is inserted
            ws = sessions[s.session_client_id]
            if prev is not None and prev.workout_session_id != ws.id:
                raise _reject("invalid_supersedes", f"set {s.client_id}: edits a set from another session")
            row = db.scalars(
                insert(SetLog)
                .values(
                    client_id=s.client_id,
                    workout_session_id=ws.id,
                    exercise_id=ids.exercises[s.exercise_slug],
                    set_no=s.set_no,
                    weight_lb=s.weight_lb,
                    reps=s.reps,
                    seconds=s.seconds,
                    rir=s.rir,
                    is_swap=s.is_swap,
                    supersedes_id=prev.id if prev else None,
                    logged_at=s.logged_at,
                )
                .on_conflict_do_nothing(index_elements=[SetLog.client_id])
                .returning(SetLog)
            ).first()
            if row is None:  # inserted concurrently by a retry of the same batch
                row = db.scalar(select(SetLog).where(SetLog.client_id == s.client_id))
            known[s.client_id] = row
            pending.remove(s)
            progressed = True
        if not progressed:
            bad = pending[0]
            raise _reject(
                "invalid_supersedes",
                f"set {bad.client_id}: supersedes unknown set {bad.supersedes_client_id}",
            )
    return {known[s.client_id].workout_session_id for s in sets}


def run_sync(
    db: Session,
    user: User,
    e: Enrollment,
    program: Program,
    sessions: list[SessionInput],
    sets: list[SetInput],
) -> SyncResult:
    ids = program_ids(db)
    path_slug = ids.path_slug(e.path_id)
    result = SyncResult(level_before=compute_stats(db, user.id, program).level)

    batch = _upsert_sessions(db, user, e, program, sessions)
    touched = {ws.id for ws in batch.values()} | _insert_sets(db, user, sets, batch)
    result.accepted_sessions = [s.client_id for s in sessions]
    result.accepted_sets = [s.client_id for s in sets]

    stored = list(db.scalars(select(WorkoutSession).where(WorkoutSession.id.in_(touched)))) if touched else []
    scored: dict[uuid.UUID, tuple[WorkoutSession, SessionScore]] = {
        wid: (next(ws for ws in stored if ws.id == wid), score)
        for wid, (_, score) in score_stored(db, program, path_slug, stored).items()
    }
    awards: list[Award] = []
    for ws, score in scored.values():
        own = program.for_path(ids.path_slug(ws.path_id) if ws.path_id else path_slug)
        kind = own.template(ids.template_code(ws.session_template_id)).kind
        mine = session_awards(str(ws.client_id), kind, score)
        awards += mine
        result.sessions.append(
            SessionResult(ws.client_id, score.cleared, score.all_on_target, sum(a.amount for a in mine))
        )

    # Full-week bonus for every week this batch touched (sessions anywhere in that week count).
    for week in sorted({ws.week for ws in stored if ws.enrollment_id == e.id}):
        week_sessions = list(
            db.scalars(
                select(WorkoutSession).where(
                    WorkoutSession.enrollment_id == e.id, WorkoutSession.week == week
                )
            )
        )
        week_scores = score_stored(db, program, path_slug, week_sessions)
        cleared = [
            ids.template_code(ws.session_template_id) for ws in week_sessions if week_scores[ws.id][1].cleared
        ]
        if is_full_week(program.for_path(path_slug), cleared):
            awards.append(full_week_award(str(e.id), week))

    result.xp_awarded = record_awards(db, user.id, awards)
    result.new_badges, badge_xp = award_badges(db, user.id, e, program)
    result.xp_awarded += badge_xp
    result.stats = refresh_stats(db, user.id, program)

    if touched:
        db.add(
            Job(
                kind="run_progression",
                payload={"user_id": str(user.id), "session_ids": sorted(str(t) for t in touched)},
            )
        )
    return result
