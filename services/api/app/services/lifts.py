"""The user's 1RMs (lb), keyed by exercise slug."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserLift
from app.services.program import program_ids


@dataclass(frozen=True)
class Lift:
    exercise: str
    one_rm_lb: float
    updated_at: dt.datetime


def user_lifts(db: Session, user_id: uuid.UUID) -> dict[str, Lift]:
    ids = program_ids(db)
    rows = db.scalars(select(UserLift).where(UserLift.user_id == user_id))
    return {
        ids.exercise_slug(r.exercise_id): Lift(
            ids.exercise_slug(r.exercise_id), float(r.one_rm_lb), r.updated_at
        )
        for r in rows
    }
