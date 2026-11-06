"""Trials and tape scans (docs/04-api.md, "Tests (Trials)" and "Scans")."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Db
from app.api.errors import ERROR_RESPONSES, ApiError
from app.api.me import StatsOut
from app.api.sync import AwardOut, LevelUp, NewBadge
from app.models import BodyScan, Enrollment, User
from app.rules.calendar import phase_display_name, session_date
from app.rules.program import Program
from app.rules.trials import frame_ratio, power_level, trial_awards, trial_complete
from app.rules.xp import Award, rank_for, scan_award
from app.services.awards import award_badges, record_awards
from app.services.program import get_program, program_ids
from app.services.stats import active_enrollment, compute_stats, refresh_stats, trial_results
from app.services.trials import upsert_trial_results

router = APIRouter(tags=["trials"], responses=ERROR_RESPONSES)


class Rewards(BaseModel):
    xp_awarded: list[AwardOut]
    stats: StatsOut
    level_up: LevelUp | None
    new_badges: list[NewBadge]


class TrialIn(BaseModel):
    results: dict[str, float | None]  # test type -> value; null clears a value; omitted tests are unchanged
    taken_on: dt.date | None = None


class TrialOut(BaseModel):
    phase_ord: int
    name: str
    start_date: dt.date
    results: dict[str, float | None]  # every test type, null when not entered
    frame_ratio: float | None
    power_level: int | None
    complete: bool


class TrialSaved(TrialOut, Rewards):
    pass


class ScanIn(BaseModel):
    shoulders_in: float = Field(gt=0, le=99.9)
    waist_in: float = Field(gt=0, le=99.9)
    with_photo: bool = False
    taken_at: AwareDatetime | None = None


class ScanOut(BaseModel):
    id: uuid.UUID
    status: str
    shoulders_in: float | None
    waist_in: float | None
    frame_ratio: float | None
    taken_at: dt.datetime


class ScanSaved(Rewards):
    scan: ScanOut
    upload_url: str | None  # photo upload arrives in M5


def _enrollment(db: Db, user: User) -> Enrollment:
    e = active_enrollment(db, user.id)
    if e is None:
        raise ApiError(404, "no_enrollment", "start a run first (POST /v1/enrollments)")
    return e


def _settle(
    db: Session, user: User, e: Enrollment, program: Program, awards: list[Award], before: int
) -> Rewards:
    new = record_awards(db, user.id, awards)
    badges, badge_xp = award_badges(db, user.id, e, program)
    stats = refresh_stats(db, user.id, program)
    return Rewards(
        xp_awarded=[AwardOut(type=a.type, amount=a.amount, source_id=a.source_id) for a in new + badge_xp],
        stats=StatsOut.of(stats),
        level_up=LevelUp(from_=before, to=stats.level, rank=rank_for(stats.level, program).name)
        if stats.level > before
        else None,
        new_badges=[
            NewBadge(slug=b.slug, name=b.name, description=b.description, xp_reward=b.xp_reward)
            for b in badges
        ],
    )


def _trial_out(program: Program, e: Enrollment, path_slug: str, ord_: int, results: dict) -> TrialOut:
    phase = program.phase_by_ord(ord_)
    full = {t.type: results.get(t.type) for t in program.tests}
    return TrialOut(
        phase_ord=ord_,
        name=phase_display_name(phase, program.path(path_slug)),
        start_date=session_date(e.started_on, phase.start_week, 1),
        results=full,
        frame_ratio=frame_ratio(full.get("shoulders_in"), full.get("waist_in")),
        power_level=power_level(full),
        complete=trial_complete(full, program),
    )


@router.put("/trials/{phase_ord}", response_model=TrialSaved, response_model_by_alias=True)
def put_trial(phase_ord: int, body: TrialIn, db: Db, user: CurrentUser) -> TrialSaved:
    """Enter Trial results (partial allowed). A complete Trial awards 500 XP once."""
    program = get_program()
    e = _enrollment(db, user)
    ids = program_ids(db)
    # A block program path (Iron Tempo) has no Trials: its 1RMs are entered instead.
    own = program.for_path(ids.path_slug(e.path_id))
    phase = next((p for p in own.phases if p.ord == phase_ord), None)
    if phase is None or not phase.is_trial:
        raise ApiError(404, "not_found", f"no Trial with phase ord {phase_ord}")
    known = {t.type for t in program.tests}
    unknown = sorted(set(body.results) - known)
    if unknown:
        raise ApiError(422, "unknown_test", f"unknown tests: {', '.join(unknown)}")
    for test, value in body.results.items():
        if value is not None and not 0 <= value <= 99_999:
            raise ApiError(422, "validation_error", f"results.{test}: must be between 0 and 99999")

    before = compute_stats(db, user.id, program).level
    taken_at = (
        dt.datetime.combine(body.taken_on, dt.time(12), tzinfo=dt.UTC)
        if body.taken_on
        else dt.datetime.now(dt.UTC)
    )
    upsert_trial_results(db, user.id, e, phase_ord, body.results, taken_at)
    results = trial_results(db, user.id, e.id).get(phase_ord, {})
    rewards = _settle(db, user, e, program, trial_awards(str(e.id), phase_ord, results, program), before)
    db.commit()
    out = _trial_out(program, e, ids.path_slug(e.path_id), phase_ord, results)
    return TrialSaved(**out.model_dump(), **rewards.model_dump(by_alias=False))


@router.get("/trials", response_model=list[TrialOut])
def list_trials(db: Db, user: CurrentUser) -> list[TrialOut]:
    """Every Trial of the active run, with whatever results are entered."""
    program = get_program()
    e = _enrollment(db, user)
    path_slug = program_ids(db).path_slug(e.path_id)
    if program.for_path(path_slug) is not program:
        return []  # a block program path (Iron Tempo) has no Trials
    entered = trial_results(db, user.id, e.id)
    return [
        _trial_out(program, e, path_slug, p.ord, entered.get(p.ord, {})) for p in program.phases if p.is_trial
    ]


def _scan_out(s: BodyScan) -> ScanOut:
    shoulders = float(s.shoulders_in) if s.shoulders_in is not None else None
    waist = float(s.waist_in) if s.waist_in is not None else None
    return ScanOut(
        id=s.id,
        status=s.status,
        shoulders_in=shoulders,
        waist_in=waist,
        frame_ratio=frame_ratio(shoulders, waist),
        taken_at=s.taken_at,
    )


@router.post("/scans", response_model=ScanSaved, status_code=201, response_model_by_alias=True)
def create_scan(body: ScanIn, db: Db, user: CurrentUser) -> ScanSaved:
    """Log a tape measurement. Photo scans arrive in M5."""
    if body.with_photo:
        raise ApiError(
            422, "photo_scans_unavailable", "photo scans are not available yet; log tape measurements"
        )
    program = get_program()
    e = _enrollment(db, user)
    before = compute_stats(db, user.id, program).level
    scan = BodyScan(
        user_id=user.id,
        status="done",
        shoulders_in=body.shoulders_in,
        waist_in=body.waist_in,
        taken_at=body.taken_at or dt.datetime.now(dt.UTC),
    )
    db.add(scan)
    db.flush()
    rewards = _settle(db, user, e, program, [scan_award(str(scan.id))], before)
    db.commit()
    db.refresh(scan)
    return ScanSaved(scan=_scan_out(scan), upload_url=None, **rewards.model_dump(by_alias=False))


@router.get("/scans", response_model=list[ScanOut])
def list_scans(db: Db, user: CurrentUser) -> list[ScanOut]:
    rows = db.scalars(select(BodyScan).where(BodyScan.user_id == user.id).order_by(BodyScan.taken_at.desc()))
    return [_scan_out(s) for s in rows]
