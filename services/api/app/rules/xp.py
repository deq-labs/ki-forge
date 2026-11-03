"""XP awards, levels and ranks (docs/03-program-rules.md §3, v1 parity rules).

Awards are `(type, amount, source_id)`; the server stores them in `xp_events` with a unique key on
`(user_id, type, source_id)`, so building the same award twice never double-counts. XP is never removed.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.rules.completion import SessionScore
from app.rules.program import Badge, Program, Rank, SessionKind

AwardType = Literal[
    "set_logged", "session_cleared", "all_on_target", "full_week", "trial_completed", "badge", "scan_logged"
]

# v1 XP table. Badge XP comes from each badge's `xp_reward` in program.json.
XP_SET_LOGGED = 5
XP_LIFT_CLEARED = 100
XP_ALL_ON_TARGET = 25  # lift sessions only
XP_CONDITIONING_CLEARED = 50
XP_FULL_WEEK = 150
XP_TRIAL_COMPLETED = 500
XP_SCAN_LOGGED = 50


@dataclass(frozen=True, slots=True)
class Award:
    type: AwardType
    amount: int
    source_id: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.type, self.source_id)


def session_awards(session_id: str, kind: SessionKind, score: SessionScore) -> list[Award]:
    """Awards for one scored session: 5 per counted set, plus the cleared and on-target bonuses.

    Set awards use each set's chain root id (`RowScore.counted`), so an edited set is not paid twice.
    """
    awards = [Award("set_logged", XP_SET_LOGGED, sid) for row in score.rows for sid in row.counted]
    if score.cleared:
        if kind == "lift":
            awards.append(Award("session_cleared", XP_LIFT_CLEARED, session_id))
            if score.all_on_target:
                awards.append(Award("all_on_target", XP_ALL_ON_TARGET, session_id))
        else:
            awards.append(Award("session_cleared", XP_CONDITIONING_CLEARED, session_id))
    return awards


def full_week_award(enrollment_id: str, week: int) -> Award:
    return Award("full_week", XP_FULL_WEEK, f"week:{enrollment_id}:{week}")


def trial_award(enrollment_id: str, phase_ord: int) -> Award:
    return Award("trial_completed", XP_TRIAL_COMPLETED, f"trial:{enrollment_id}:{phase_ord}")


def badge_award(badge: Badge) -> Award:
    return Award("badge", badge.xp_reward, f"badge:{badge.slug}")


def scan_award(scan_id: str) -> Award:
    return Award("scan_logged", XP_SCAN_LOGGED, scan_id)


def dedupe(awards: Iterable[Award]) -> list[Award]:
    """Keep the first award per `(type, source_id)`, as the database's unique key does."""
    seen: set[tuple[str, str]] = set()
    out = []
    for a in awards:
        if a.key not in seen:
            seen.add(a.key)
            out.append(a)
    return out


def total_xp(awards: Iterable[Award]) -> int:
    return sum(a.amount for a in dedupe(awards))


# --- levels and ranks ------------------------------------------------------------------------------------


def xp_for_level(level_: int) -> int:
    """Total XP needed to be `level_` (level 1 needs 0)."""
    if level_ < 1:
        raise ValueError(f"level must be >= 1, got {level_}")
    k = level_ - 1
    return 50 * k * k + 350 * k


def level(xp: int) -> int:
    """`floor((-350 + sqrt(350² + 200·xp)) / 100) + 1`, corrected so it is exact for every integer XP."""
    if xp < 0:
        raise ValueError(f"xp must be >= 0, got {xp}")
    lv = (math.isqrt(350 * 350 + 200 * xp) - 350) // 100 + 1
    while lv > 1 and xp_for_level(lv) > xp:
        lv -= 1
    while xp_for_level(lv + 1) <= xp:
        lv += 1
    return lv


@dataclass(frozen=True, slots=True)
class LevelProgress:
    level: int
    xp: int
    xp_into_level: int
    xp_to_next: int


def level_progress(xp: int) -> LevelProgress:
    lv = level(xp)
    floor_, next_ = xp_for_level(lv), xp_for_level(lv + 1)
    return LevelProgress(level=lv, xp=xp, xp_into_level=xp - floor_, xp_to_next=next_ - xp)


def rank_for(level_: int, program: Program) -> Rank:
    """Highest rank whose `from_level` is at or below the level."""
    current = program.ranks[0]
    for r in program.ranks:
        if r.from_level <= level_:
            current = r
    return current
