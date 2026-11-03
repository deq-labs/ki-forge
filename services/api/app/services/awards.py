"""Writing XP awards and badges. Every award is idempotent through `xp_events (user_id, type, source_id)`."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import Text, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import BodyScan, Enrollment, UserBadge, WorkoutSession, XpEvent
from app.rules.badges import BadgeMetrics, earned_badges, frame_ratio_vs_target
from app.rules.program import Badge, Program
from app.rules.trials import latest_frame_ratio
from app.rules.xp import Award, badge_award, dedupe, level
from app.services.program import get_program, program_ids
from app.services.stats import frame_readings


def record_awards(db: Session, user_id: uuid.UUID, awards: Iterable[Award]) -> list[Award]:
    """Insert awards, skipping any already recorded. Returns only the newly recorded ones."""
    new: list[Award] = []
    for a in dedupe(awards):
        inserted = db.execute(
            insert(XpEvent)
            .values(user_id=user_id, type=a.type, amount=a.amount, source_id=a.source_id)
            .on_conflict_do_nothing(index_elements=[XpEvent.user_id, XpEvent.type, XpEvent.source_id])
            .returning(XpEvent.id)
        ).first()
        if inserted is not None:
            new.append(a)
    return new


def _count(db: Session, user_id: uuid.UUID, type_: str) -> int:
    return db.scalar(select(func.count()).where(XpEvent.user_id == user_id, XpEvent.type == type_)) or 0


def badge_metrics(db: Session, user_id: uuid.UUID, enrollment: Enrollment | None) -> BadgeMetrics:
    total = (
        db.scalar(select(func.coalesce(func.sum(XpEvent.amount), 0)).where(XpEvent.user_id == user_id)) or 0
    )
    garage_cleared = db.scalar(
        select(func.count())
        .select_from(XpEvent)
        .join(WorkoutSession, cast(WorkoutSession.client_id, Text) == XpEvent.source_id)
        .where(
            XpEvent.user_id == user_id,
            XpEvent.type == "session_cleared",
            WorkoutSession.user_id == user_id,
            WorkoutSession.garage_mode.is_(True),
        )
    )
    scans = db.scalar(select(func.count()).where(BodyScan.user_id == user_id)) or 0
    vs_target = None
    if enrollment is not None:
        path = get_program().path(program_ids(db).path_slug(enrollment.path_id))
        vs_target = frame_ratio_vs_target(latest_frame_ratio(frame_readings(db, user_id)), path)
    return BadgeMetrics(
        sessions_cleared=_count(db, user_id, "session_cleared"),
        full_weeks=_count(db, user_id, "full_week"),
        garage_sessions_cleared=garage_cleared or 0,
        scans=scans,
        level=level(int(total)),
        frame_ratio_vs_target=vs_target,
    )


def award_badges(
    db: Session, user_id: uuid.UUID, enrollment: Enrollment | None, program: Program
) -> tuple[list[Badge], list[Award]]:
    """Award every newly earned badge once, with its XP.

    Repeats while badge XP unlocks more badges (badge XP can reach the level badge).
    """
    ids = program_ids(db)
    new_badges: list[Badge] = []
    new_awards: list[Award] = []
    for _ in range(len(program.badges)):
        held = set(db.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == user_id)))
        held_slugs = {slug for slug, bid in ids.badges.items() if bid in held}
        earned = earned_badges(program, badge_metrics(db, user_id, enrollment), held_slugs)
        if not earned:
            break
        for b in earned:
            row = db.execute(
                insert(UserBadge)
                .values(user_id=user_id, badge_id=ids.badges[b.slug])
                .on_conflict_do_nothing()
                .returning(UserBadge.badge_id)
            ).first()
            if row is not None:
                new_badges.append(b)
                new_awards += record_awards(db, user_id, [badge_award(b)])
    return new_badges, new_awards
