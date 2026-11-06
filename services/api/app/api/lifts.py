"""1RMs: GET /v1/me/lifts and PUT /v1/me/lifts (Iron Tempo % of 1RM targets, #65)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import CurrentUser, Db
from app.api.errors import ERROR_RESPONSES, ApiError
from app.models import UserLift
from app.services.lifts import user_lifts
from app.services.program import get_program, program_ids
from app.services.stats import active_enrollment

router = APIRouter(tags=["me"], responses=ERROR_RESPONSES)


class LiftOut(BaseModel):
    exercise: str
    name: str
    one_rm_lb: float | None  # None = not entered yet
    updated_at: dt.datetime | None


class LiftsOut(BaseModel):
    lifts: list[LiftOut]  # the 1RM lifts of the active run's program (else every program's), in order


class LiftsPut(BaseModel):
    # exercise slug -> 1RM in lb; null clears it. Lifts not listed are left as they are.
    lifts: dict[str, float | None] = Field(min_length=1)


def _lift_slugs(db: Db, user) -> list[str]:
    program = get_program()
    e = active_enrollment(db, user.id)
    if e is not None:
        own = program.for_path(program_ids(db).path_slug(e.path_id))
        if own.one_rm_lifts:
            return list(own.one_rm_lifts)
    seen: dict[str, None] = {}
    for p in program.programs.values():
        seen.update(dict.fromkeys(p.one_rm_lifts))
    return list(seen)


def _out(db: Db, user) -> LiftsOut:
    program = get_program()
    have = user_lifts(db, user.id)
    return LiftsOut(
        lifts=[
            LiftOut(
                exercise=slug,
                name=program.exercise(slug).name,
                one_rm_lb=have[slug].one_rm_lb if slug in have else None,
                updated_at=have[slug].updated_at if slug in have else None,
            )
            for slug in _lift_slugs(db, user)
        ]
    )


@router.get("/me/lifts", response_model=LiftsOut)
def read_lifts(db: Db, user: CurrentUser) -> LiftsOut:
    return _out(db, user)


@router.put("/me/lifts", response_model=LiftsOut)
def put_lifts(body: LiftsPut, db: Db, user: CurrentUser) -> LiftsOut:
    """Set or clear 1RMs (lb). Each lift set here counts as re-tested now."""
    ids = program_ids(db)
    allowed = {s for p in get_program().programs.values() for s in p.one_rm_lifts}
    for slug, lb in body.lifts.items():
        if slug not in allowed:
            raise ApiError(422, "validation_error", f"lifts.{slug}: not a 1RM lift")
        if lb is not None and not 0 < lb < 2000:
            raise ApiError(422, "validation_error", f"lifts.{slug}: must be between 0 and 2000 lb")
    for slug, lb in body.lifts.items():
        if lb is None:
            db.execute(
                delete(UserLift).where(
                    UserLift.user_id == user.id, UserLift.exercise_id == ids.exercises[slug]
                )
            )
            continue
        db.execute(
            insert(UserLift)
            .values(user_id=user.id, exercise_id=ids.exercises[slug], one_rm_lb=lb)
            .on_conflict_do_update(
                index_elements=[UserLift.user_id, UserLift.exercise_id],
                set_={"one_rm_lb": lb, "updated_at": func.now()},
            )
        )
    db.commit()
    return _out(db, user)
