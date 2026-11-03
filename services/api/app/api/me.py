"""Me and enrollments (docs/04-api.md, "Me")."""

from __future__ import annotations

import datetime as dt
import uuid
from zoneinfo import available_timezones

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, Db
from app.api.errors import ERROR_RESPONSES, ApiError
from app.models import BadgeRow, Enrollment, User, UserBadge
from app.services.program import get_program, program_ids
from app.services.stats import Stats, active_enrollment, compute_stats

router = APIRouter(tags=["me"], responses=ERROR_RESPONSES)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str
    units: str
    timezone: str
    keep_photos: bool


class EnrollmentOut(BaseModel):
    id: uuid.UUID
    path_slug: str
    start_date: dt.date
    cycle: int
    garage_mode_default: bool
    status: str


class StatsOut(BaseModel):
    total_xp: int
    level: int
    rank: str
    xp_into_level: int
    xp_to_next: int
    power_level: int | None
    frame_ratio: float | None
    sessions_cleared: int

    @classmethod
    def of(cls, s: Stats) -> StatsOut:
        return cls(**s.__dict__)


class EarnedBadgeOut(BaseModel):
    slug: str
    name: str
    description: str
    earned_at: dt.datetime


class MeOut(BaseModel):
    user: UserOut
    enrollment: EnrollmentOut | None
    stats: StatsOut
    badges: list[EarnedBadgeOut]


class MePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    units: str | None = Field(default=None, pattern="^(imperial|metric)$")
    timezone: str | None = None
    keep_photos: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None and v not in available_timezones():
            raise ValueError(f"unknown time zone {v!r}")
        return v


def _monday(v: dt.date | None) -> dt.date | None:
    if v is not None and v.isoweekday() != 1:
        raise ValueError("start_date must be a Monday (the Monday of the Trial 0 week)")
    return v


class EnrollmentCreate(BaseModel):
    path_slug: str
    start_date: dt.date
    garage_mode_default: bool = False

    @field_validator("start_date")
    @classmethod
    def _check_monday(cls, v: dt.date | None) -> dt.date | None:
        return _monday(v)


class EnrollmentPatch(BaseModel):
    path_slug: str | None = None
    start_date: dt.date | None = None
    garage_mode_default: bool | None = None

    @field_validator("start_date")
    @classmethod
    def _check_monday(cls, v: dt.date | None) -> dt.date | None:
        return _monday(v)


def enrollment_out(db: Db, e: Enrollment) -> EnrollmentOut:
    return EnrollmentOut(
        id=e.id,
        path_slug=program_ids(db).path_slug(e.path_id),
        start_date=e.started_on,
        cycle=e.cycle,
        garage_mode_default=e.garage_mode_default,
        status=e.status,
    )


def _path_id(db: Db, slug: str) -> int:
    ids = program_ids(db)
    if slug not in ids.paths or slug not in get_program().paths:
        raise ApiError(422, "validation_error", f"path_slug: unknown path {slug!r}")
    return ids.paths[slug]


def _me(db: Db, user: User) -> MeOut:
    enrollment = active_enrollment(db, user.id)
    badges = db.execute(
        select(BadgeRow.slug, BadgeRow.name, BadgeRow.description, UserBadge.earned_at)
        .join(UserBadge, UserBadge.badge_id == BadgeRow.id)
        .where(UserBadge.user_id == user.id)
        .order_by(UserBadge.earned_at, BadgeRow.id)
    )
    return MeOut(
        user=UserOut.model_validate(user, from_attributes=True),
        enrollment=enrollment_out(db, enrollment) if enrollment else None,
        stats=StatsOut.of(compute_stats(db, user.id)),
        badges=[EarnedBadgeOut(slug=s, name=n, description=d, earned_at=t) for s, n, d, t in badges],
    )


@router.get("/me", response_model=MeOut)
def read_me(db: Db, user: CurrentUser) -> MeOut:
    return _me(db, user)


@router.patch("/me", response_model=MeOut)
def update_me(body: MePatch, db: Db, user: CurrentUser) -> MeOut:
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            raise ApiError(422, "validation_error", f"{field}: may not be null")
        setattr(user, field, value)
    db.commit()
    return _me(db, user)


@router.post("/enrollments", response_model=EnrollmentOut, status_code=201)
def create_enrollment(body: EnrollmentCreate, db: Db, user: CurrentUser) -> EnrollmentOut:
    if active_enrollment(db, user.id) is not None:
        raise ApiError(409, "conflict", "you already have an active run; finish or change it instead")
    e = Enrollment(
        user_id=user.id,
        program_id=program_ids(db).program_id,
        path_id=_path_id(db, body.path_slug),
        started_on=body.start_date,
        garage_mode_default=body.garage_mode_default,
    )
    db.add(e)
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent create hit the one_active_enrollment index
        db.rollback()
        raise ApiError(409, "conflict", "you already have an active run") from exc
    return enrollment_out(db, e)


@router.patch("/enrollments/{enrollment_id}", response_model=EnrollmentOut)
def update_enrollment(
    enrollment_id: uuid.UUID, body: EnrollmentPatch, db: Db, user: CurrentUser
) -> EnrollmentOut:
    """Change path, start date or garage default. A new path applies to sessions not yet started."""
    e = db.get(Enrollment, enrollment_id)
    if e is None or e.user_id != user.id:
        raise ApiError(404, "not_found", "enrollment not found")
    changes = body.model_dump(exclude_unset=True)
    if any(v is None for v in changes.values()):
        raise ApiError(422, "validation_error", "fields may not be null")
    if "path_slug" in changes:
        e.path_id = _path_id(db, changes["path_slug"])
    if "start_date" in changes:
        e.started_on = changes["start_date"]
    if "garage_mode_default" in changes:
        e.garage_mode_default = changes["garage_mode_default"]
    db.commit()
    return enrollment_out(db, e)
