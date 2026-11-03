"""Stored workout sessions → rules-engine inputs and scores."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models import Enrollment, SetLog, User, WorkoutSession
from app.rules.calendar import phase_for, week_for
from app.rules.completion import LoggedSet, SessionScore, score_session
from app.rules.program import Program
from app.rules.sessions import BuiltSession, build_session
from app.services.program import program_ids


def today_for(user: User) -> dt.date:
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:  # noqa: BLE001 - a bad stored zone must not break the calendar
        tz = dt.UTC
    return dt.datetime.now(tz).date()


def current_week(enrollment: Enrollment, user: User) -> int:
    """Program week of today in the user's time zone (negative before the start date)."""
    return week_for(today_for(user), enrollment.started_on)


def built_for(
    program: Program, enrollment_path: str, code: str, week: int, garage_mode: bool
) -> BuiltSession | None:
    phase = phase_for(week, program)
    if phase is None:
        return None
    return build_session(
        program, program.template(code), phase, program.path(enrollment_path), garage_mode=garage_mode
    )


def logged_sets(db: Session, session_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[LoggedSet]]:
    """Every stored set (all edit rows) per workout session, as `LoggedSet`s identified by client_id."""
    session_ids = list(session_ids)
    out: dict[uuid.UUID, list[LoggedSet]] = {sid: [] for sid in session_ids}
    if not session_ids:
        return out
    ids = program_ids(db)
    prev = aliased(SetLog)
    rows = db.execute(
        select(SetLog, prev.client_id)
        .outerjoin(prev, prev.id == SetLog.supersedes_id)
        .where(SetLog.workout_session_id.in_(session_ids))
        .order_by(SetLog.logged_at, SetLog.set_no)
    )
    for s, supersedes_client in rows:
        out[s.workout_session_id].append(
            LoggedSet(
                id=str(s.client_id),
                exercise=ids.exercise_slug(s.exercise_id),
                reps=s.reps,
                logged_at=s.logged_at,
                set_no=s.set_no,
                weight_lb=float(s.weight_lb),
                rir=s.rir,
                supersedes=str(supersedes_client) if supersedes_client else None,
            )
        )
    return out


def score_stored(
    db: Session, program: Program, path_slug: str, sessions: Iterable[WorkoutSession]
) -> dict[uuid.UUID, tuple[BuiltSession, SessionScore]]:
    """Build and score stored sessions with the enrollment's current path. Keyed by workout session id."""
    sessions = list(sessions)
    ids = program_ids(db)
    sets = logged_sets(db, (s.id for s in sessions))
    out = {}
    for ws in sessions:
        built = built_for(
            program, path_slug, ids.template_code(ws.session_template_id), ws.week, ws.garage_mode
        )
        if built is not None:
            out[ws.id] = (built, score_session(built, sets[ws.id]))
    return out
