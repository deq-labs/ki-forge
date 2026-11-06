"""POST /v1/sync (docs/04-api.md, "Sync")."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel, Field

from app.api.deps import CurrentUser, Db
from app.api.errors import ERROR_RESPONSES, ApiError
from app.api.me import StatsOut
from app.rules.xp import rank_for
from app.services.program import get_program
from app.services.stats import active_enrollment
from app.services.sync import SessionInput, SetInput, run_sync

router = APIRouter(tags=["sync"], responses=ERROR_RESPONSES)

MAX_BATCH = 500


class SyncSession(BaseModel):
    client_id: uuid.UUID
    template_code: str
    week: int = Field(ge=0)
    garage_mode: bool = False
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None


class SyncSet(BaseModel):
    client_id: uuid.UUID
    session_client_id: uuid.UUID
    exercise_slug: str
    set_no: int = Field(ge=1, le=50)
    weight_lb: float = Field(default=0, ge=0, le=2000)
    reps: int | None = Field(default=None, ge=0, le=1000)
    seconds: int | None = Field(default=None, ge=0, le=32767)
    rir: int | None = Field(default=None, ge=0, le=5)
    is_swap: bool = False
    supersedes_client_id: uuid.UUID | None = None
    logged_at: AwareDatetime
    # The session row's `key` (from GET /v1/week) for a block round, where an exercise can be in two rows.
    slot: str | None = Field(default=None, max_length=16)


class SyncIn(BaseModel):
    sessions: list[SyncSession] = Field(default_factory=list, max_length=MAX_BATCH)
    sets: list[SyncSet] = Field(default_factory=list, max_length=MAX_BATCH)


class Accepted(BaseModel):
    sessions: list[uuid.UUID]
    sets: list[uuid.UUID]


class AwardOut(BaseModel):
    type: str
    amount: int
    source_id: str


class LevelUp(BaseModel):
    from_: int = Field(alias="from", serialization_alias="from")
    to: int
    rank: str

    model_config = {"populate_by_name": True}


class NewBadge(BaseModel):
    slug: str
    name: str
    description: str
    xp_reward: int


class SessionOutcome(BaseModel):
    client_id: uuid.UUID
    cleared: bool
    all_on_target: bool
    xp: int  # everything the session earns: its counted sets plus the cleared / on-target bonuses


class SyncOut(BaseModel):
    accepted: Accepted
    xp_awarded: list[AwardOut]  # only awards new in this request; a replay returns []
    stats: StatsOut
    level_up: LevelUp | None
    new_badges: list[NewBadge]
    sessions: list[SessionOutcome]


@router.post("/sync", response_model=SyncOut, response_model_by_alias=True)
def sync(body: SyncIn, db: Db, user: CurrentUser) -> SyncOut:
    """Upsert logged sessions and sets; returns authoritative stats. Idempotent: replays award nothing."""
    e = active_enrollment(db, user.id)
    if e is None:
        raise ApiError(404, "no_enrollment", "start a run first (POST /v1/enrollments)")
    if len({s.client_id for s in body.sessions}) != len(body.sessions) or len(
        {s.client_id for s in body.sets}
    ) != len(body.sets):
        raise ApiError(422, "duplicate_client_id", "a client_id appears twice in the batch")
    program = get_program()
    result = run_sync(
        db,
        user,
        e,
        program,
        [SessionInput(**s.model_dump()) for s in body.sessions],
        [SetInput(**s.model_dump()) for s in body.sets],
    )
    db.commit()
    stats = result.stats
    assert stats is not None
    return SyncOut(
        accepted=Accepted(sessions=result.accepted_sessions, sets=result.accepted_sets),
        xp_awarded=[AwardOut(type=a.type, amount=a.amount, source_id=a.source_id) for a in result.xp_awarded],
        stats=StatsOut.of(stats),
        level_up=LevelUp(from_=result.level_before, to=stats.level, rank=rank_for(stats.level, program).name)
        if stats.level > result.level_before
        else None,
        new_badges=[
            NewBadge(slug=b.slug, name=b.name, description=b.description, xp_reward=b.xp_reward)
            for b in result.new_badges
        ],
        sessions=[
            SessionOutcome(client_id=s.client_id, cleared=s.cleared, all_on_target=s.all_on_target, xp=s.xp)
            for s in result.sessions
        ],
    )
