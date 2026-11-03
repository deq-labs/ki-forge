"""A user's stats: computed by the rules engine from xp_events, test_results and body_scans.

`user_stats` is a cache of the stored columns (total_xp, level, power_level); `refresh_stats` rewrites it
and `compute_stats` can always rebuild everything from the source rows.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import BodyScan, Enrollment, TestResult, UserStats, XpEvent
from app.rules.program import Program
from app.rules.trials import FrameReading, TestResults, latest_frame_ratio, latest_power_level
from app.rules.xp import level_progress, rank_for
from app.services.program import get_program, program_ids


@dataclass(frozen=True)
class Stats:
    total_xp: int
    level: int
    rank: str
    xp_into_level: int
    xp_to_next: int
    power_level: int | None
    frame_ratio: float | None
    sessions_cleared: int


def active_enrollment(db: Session, user_id: uuid.UUID) -> Enrollment | None:
    return db.scalar(select(Enrollment).where(Enrollment.user_id == user_id, Enrollment.status == "active"))


def trial_results(db: Session, user_id: uuid.UUID, enrollment_id: uuid.UUID) -> dict[int, dict[str, float]]:
    """Entered test values per Trial phase ord for one enrollment."""
    ids = program_ids(db)
    out: dict[int, dict[str, float]] = {}
    rows = db.execute(
        select(TestResult.phase_id, TestResult.test, TestResult.value).where(
            TestResult.user_id == user_id, TestResult.enrollment_id == enrollment_id
        )
    )
    for phase_id, test, value in rows:
        if phase_id is None:
            continue
        v = float(value)
        out.setdefault(ids.phase_ord(phase_id), {})[test] = int(v) if v.is_integer() else v
    return out


def frame_readings(db: Session, user_id: uuid.UUID) -> list[FrameReading]:
    """Tape measurements from every Trial and scan, each at the time it was taken."""
    readings: list[FrameReading] = []
    trial_rows = db.execute(
        select(
            TestResult.enrollment_id,
            TestResult.phase_id,
            TestResult.test,
            TestResult.value,
            TestResult.taken_at,
        ).where(TestResult.user_id == user_id, TestResult.test.in_(("shoulders_in", "waist_in")))
    )
    by_trial: dict[tuple, dict[str, tuple[float, dt.datetime]]] = {}
    for enrollment_id, phase_id, test, value, taken_at in trial_rows:
        by_trial.setdefault((enrollment_id, phase_id), {})[test] = (float(value), taken_at)
    for tests in by_trial.values():
        if "shoulders_in" in tests and "waist_in" in tests:
            at = max(tests["shoulders_in"][1], tests["waist_in"][1])
            readings.append(FrameReading(at, tests["shoulders_in"][0], tests["waist_in"][0]))
    scans = db.execute(
        select(BodyScan.shoulders_in, BodyScan.waist_in, BodyScan.taken_at).where(BodyScan.user_id == user_id)
    )
    for shoulders, waist, taken_at in scans:
        readings.append(
            FrameReading(taken_at, float(shoulders) if shoulders else None, float(waist) if waist else None)
        )
    return readings


def compute_stats(db: Session, user_id: uuid.UUID, program: Program | None = None) -> Stats:
    program = program or get_program()
    total = (
        db.scalar(select(func.coalesce(func.sum(XpEvent.amount), 0)).where(XpEvent.user_id == user_id)) or 0
    )
    cleared = db.scalar(
        select(func.count()).where(XpEvent.user_id == user_id, XpEvent.type == "session_cleared")
    )
    progress = level_progress(int(total))
    enrollment = active_enrollment(db, user_id)
    trials: dict[int, TestResults] = trial_results(db, user_id, enrollment.id) if enrollment else {}
    return Stats(
        total_xp=progress.xp,
        level=progress.level,
        rank=rank_for(progress.level, program).name,
        xp_into_level=progress.xp_into_level,
        xp_to_next=progress.xp_to_next,
        power_level=latest_power_level(trials),
        frame_ratio=latest_frame_ratio(frame_readings(db, user_id)),
        sessions_cleared=int(cleared or 0),
    )


def refresh_stats(db: Session, user_id: uuid.UUID, program: Program | None = None) -> Stats:
    """Recompute stats and write the user_stats cache row. The caller commits."""
    stats = compute_stats(db, user_id, program)
    values = {"total_xp": stats.total_xp, "level": stats.level, "power_level": stats.power_level or 0}
    db.execute(
        insert(UserStats)
        .values(user_id=user_id, **values)
        .on_conflict_do_update(index_elements=[UserStats.user_id], set_={**values, "updated_at": func.now()})
    )
    return stats
