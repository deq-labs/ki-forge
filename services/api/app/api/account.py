"""Workbook import, data export and account deletion (docs/04-api.md, "Import" and "Account")."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import select, update

from app.api.deps import CurrentUser, Db
from app.api.errors import ERROR_RESPONSES, ApiError
from app.api.me import StatsOut
from app.api.sync import AwardOut
from app.jobs import enqueue
from app.models import Base, SetLog, User, WorkoutSession
from app.services.importer import Totals, import_workbook
from app.services.program import get_program
from app.services.restore import restore_export
from app.tools.import_workbook import WorkbookError, open_workbook

router = APIRouter(tags=["account"], responses=ERROR_RESPONSES)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DELETE_EXPECTED = dt.timedelta(minutes=5)


class TotalsOut(BaseModel):
    total_xp: int | None
    level: int | None
    rank: str | None
    xp_to_next: int | None
    power_level: int | None
    frame_ratio: float | str | None
    sessions_cleared: int | None

    @classmethod
    def of(cls, t: Totals) -> TotalsOut:
        return cls(**t.__dict__)


class MismatchOut(BaseModel):
    location: str
    workbook: Any
    engine: Any
    explained: str | None


class ImportOut(BaseModel):
    committed: bool
    path_slug: str
    start_date: dt.date
    sessions: int  # sessions with at least one logged set
    sets: int
    trials_entered: int
    computed: TotalsOut  # the rules engine on the workbook's inputs (no badges: the workbook has none)
    workbook: TotalsOut | None  # the workbook's own cached totals; null if it was never saved by Excel/Sheets
    mismatches: list[
        MismatchOut
    ]  # parity report; an explained mismatch means the workbook contradicts itself
    warnings: list[str]
    xp_awarded: list[AwardOut]  # commit only: awards new in this request
    stats: StatsOut | None  # commit only: your stats afterwards (includes badge XP)


@router.post("/import/workbook", response_model=ImportOut)
async def import_workbook_endpoint(
    file: UploadFile, db: Db, user: CurrentUser, commit: bool = False
) -> ImportOut:
    """Import a Ki Forge Excel workbook. Dry run by default; `?commit=true` writes. Re-import is a no-op."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "too_large", "workbook is larger than 10 MB")
    program = get_program()
    try:
        wb = open_workbook(raw, require_cached=False)
        outcome = import_workbook(db, user, wb, program, commit=commit)
    except WorkbookError as exc:
        raise ApiError(422, "invalid_workbook", str(exc)) from exc
    if commit:
        db.commit()
    data = outcome.data
    return ImportOut(
        committed=outcome.committed,
        path_slug=data.path,
        start_date=data.start_date,
        sessions=len(data.sessions),
        sets=sum(len(s.sets) for s in data.sessions),
        trials_entered=sum(1 for t in data.trials.values() if any(v is not None for v in t.values())),
        computed=TotalsOut.of(outcome.computed),
        workbook=TotalsOut.of(outcome.workbook) if outcome.workbook else None,
        mismatches=[MismatchOut(**m.__dict__) for m in outcome.mismatches],
        warnings=list(data.warnings),
        xp_awarded=[
            AwardOut(type=a.type, amount=a.amount, source_id=a.source_id) for a in outcome.xp_awarded
        ],
        stats=StatsOut.of(outcome.stats) if outcome.stats else None,
    )


class RestoreOut(BaseModel):
    xp_awarded: list[AwardOut]
    stats: StatsOut


class ExportOut(BaseModel):
    format_version: int
    exported_at: dt.datetime
    user_id: uuid.UUID
    tables: dict[str, list[dict[str, Any]]]


def user_tables() -> list[str]:
    """Every table holding a user's data: `users` plus each table with a `user_id` column, plus set_logs."""
    names = [t.name for t in Base.metadata.sorted_tables if "user_id" in t.columns]
    return ["users", *names, "set_logs"]


@router.get("/export", response_model=ExportOut)
def export(db: Db, user: CurrentUser) -> ExportOut:
    """All of your data as JSON."""
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in Base.metadata.sorted_tables:
        if table.name == "users":
            stmt = select(table).where(table.c.id == user.id)
        elif "user_id" in table.columns:
            stmt = select(table).where(table.c.user_id == user.id)
        elif table.name == "set_logs":
            sessions = select(WorkoutSession.id).where(WorkoutSession.user_id == user.id)
            stmt = select(table).where(SetLog.workout_session_id.in_(sessions)).order_by(SetLog.logged_at)
        else:
            continue
        tables[table.name] = [jsonable_encoder(dict(r._mapping)) for r in db.execute(stmt)]
    return ExportOut(format_version=1, exported_at=dt.datetime.now(dt.UTC), user_id=user.id, tables=tables)


class DeleteOut(BaseModel):
    status: str
    expected_completion_at: dt.datetime


@router.delete("/me", response_model=DeleteOut, status_code=202)
def delete_me(db: Db, user: CurrentUser) -> DeleteOut:
    """Schedule deletion of your account and all your data. You are signed out immediately."""
    db.execute(update(User).where(User.id == user.id).values(deleted_at=dt.datetime.now(dt.UTC)))
    enqueue(db, "delete_user", {"user_id": str(user.id)})
    db.commit()
    return DeleteOut(status="scheduled", expected_completion_at=dt.datetime.now(dt.UTC) + DELETE_EXPECTED)


@router.post("/import/export", response_model=RestoreOut)
def import_export(body: ExportOut, db: Db, user: CurrentUser) -> RestoreOut:
    """Re-create an export (`GET /v1/export`) in a fresh account. Awards are recomputed."""
    awards, stats = restore_export(db, user, jsonable_encoder(body), get_program())
    db.commit()
    return RestoreOut(
        xp_awarded=[AwardOut(type=a.type, amount=a.amount, source_id=a.source_id) for a in awards],
        stats=StatsOut.of(stats),
    )
