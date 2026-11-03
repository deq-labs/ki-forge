"""Workbook import through the API: a dry run by default, `commit=True` writes through the sync path.

Re-importing is idempotent: sessions and sets carry the importer's UUID5 ids, Trials upsert, and every
award has a stable source id.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.models import Enrollment, User
from app.rules.calendar import session_date
from app.rules.program import Program
from app.rules.trials import frame_ratio, latest_power_level, trial_awards
from app.rules.xp import Award, level_progress, rank_for
from app.services.awards import award_badges, record_awards
from app.services.program import program_ids
from app.services.stats import Stats, active_enrollment, refresh_stats
from app.services.sync import SessionInput, SetInput, run_sync
from app.services.trials import upsert_trial_results
from app.tools.import_workbook import Workbook, WorkbookImport, has_cached_values, read_workbook, score_import
from app.tools.parity import Mismatch, check


@dataclass(frozen=True)
class Totals:
    total_xp: int
    level: int
    rank: str
    xp_to_next: int
    power_level: int | None
    frame_ratio: float | str | None  # the workbook shows "Log Trial 0" before any ratio
    sessions_cleared: int


@dataclass
class ImportOutcome:
    data: WorkbookImport
    computed: Totals
    workbook: Totals | None
    mismatches: list[Mismatch]
    committed: bool = False
    xp_awarded: list[Award] = field(default_factory=list)
    stats: Stats | None = None


def _computed(data: WorkbookImport, program: Program) -> Totals:
    result = score_import(data, program)
    progress = level_progress(result.total_xp)
    ratio = None
    for ord_ in sorted(data.trials, reverse=True):
        t = data.trials[ord_]
        ratio = frame_ratio(t.get("shoulders_in"), t.get("waist_in"))
        if ratio is not None:
            break
    return Totals(
        total_xp=result.total_xp,
        level=progress.level,
        rank=rank_for(progress.level, program).name,
        xp_to_next=progress.xp_to_next,
        power_level=latest_power_level(data.trials),
        frame_ratio=ratio,
        sessions_cleared=sum(s.cleared for s in result.scores.values()),
    )


def _workbook_totals(wb: Workbook) -> Totals | None:
    if not has_cached_values(wb):
        return None
    c = wb.values["Start Here"]

    def num(ref: str) -> Any:
        v = c[ref].value
        return int(v) if isinstance(v, float) and v.is_integer() else v

    return Totals(
        total_xp=num("F6"),
        level=num("F7"),
        rank=c["F8"].value,
        xp_to_next=num("F9"),
        power_level=num("F13"),
        frame_ratio=num("F12"),
        sessions_cleared=num("F14"),
    )


def _enrollment_for(db: Session, user: User, data: WorkbookImport) -> Enrollment:
    ids = program_ids(db)
    e = active_enrollment(db, user.id)
    if e is None:
        e = Enrollment(
            user_id=user.id,
            program_id=ids.program_id,
            path_id=ids.paths[data.path],
            started_on=data.start_date,
        )
        db.add(e)
        db.flush()
        return e
    if e.started_on != data.start_date or ids.path_slug(e.path_id) != data.path:
        raise ApiError(
            409,
            "enrollment_mismatch",
            f"your active run is {ids.path_slug(e.path_id)} from {e.started_on}; the workbook is {data.path} "
            f"from {data.start_date}",
        )
    return e


def import_workbook(
    db: Session, user: User, wb: Workbook, program: Program, *, commit: bool
) -> ImportOutcome:
    data = read_workbook(wb, program)
    outcome = ImportOutcome(
        data=data,
        computed=_computed(data, program),
        workbook=_workbook_totals(wb),
        mismatches=list(check(wb, program).mismatches) if has_cached_values(wb) else [],
    )
    if not commit:
        return outcome

    e = _enrollment_for(db, user, data)
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:  # noqa: BLE001
        tz = dt.UTC

    def noon(day: dt.date) -> dt.datetime:
        return dt.datetime.combine(day, dt.time(12), tzinfo=tz)

    sessions = [
        SessionInput(
            client_id=uuid.UUID(s.client_id),
            template_code=s.code,
            week=s.week,
            garage_mode=s.garage_mode,
            started_at=noon(s.date),
        )
        for s in data.sessions
    ]
    sets = [
        SetInput(
            client_id=uuid.UUID(st.id),
            session_client_id=uuid.UUID(s.client_id),
            exercise_slug=st.exercise,
            set_no=st.set_no,
            weight_lb=st.weight_lb,
            logged_at=noon(s.date),
            reps=st.reps,
            rir=st.rir,
            is_swap=row.garage,
        )
        for s in data.sessions
        for row in s.rows
        for st in row.sets
    ]
    synced = run_sync(db, user, e, program, sessions, sets)
    awards: list[Award] = []
    for ord_, results in data.trials.items():
        entered = {k: v for k, v in results.items() if v is not None}
        if not entered:
            continue
        start_week = program.phase_by_ord(ord_).start_week
        upsert_trial_results(
            db, user.id, e, ord_, entered, noon(session_date(data.start_date, start_week, 1))
        )
        awards += trial_awards(str(e.id), ord_, results, program)
    new = record_awards(db, user.id, awards)
    _, badge_xp = award_badges(db, user.id, e, program)
    outcome.xp_awarded = synced.xp_awarded + new + badge_xp
    outcome.stats = refresh_stats(db, user.id, program)
    outcome.committed = True
    return outcome
