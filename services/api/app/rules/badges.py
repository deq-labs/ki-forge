"""Badges (docs/03-program-rules.md §6).

Rules are data in program.json: `{"metric": <name>, "gte": <number>}`.

Callers compute the metrics (see `BadgeMetrics`) after every sync; `earned_badges` returns the badges
newly earned, skipping any already held, so each is awarded once.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal

from app.rules.program import Badge, Program, TrainingPath


@dataclass(frozen=True, slots=True)
class BadgeMetrics:
    sessions_cleared: int = 0
    full_weeks: int = 0
    garage_sessions_cleared: int = 0
    scans: int = 0
    level: int = 1
    frame_ratio_vs_target: float | None = None  # latest frame ratio minus the path's target; None if no ratio

    def as_mapping(self) -> Mapping[str, float | None]:
        return asdict(self)


def frame_ratio_vs_target(ratio: float | None, path: TrainingPath) -> float | None:
    if ratio is None:
        return None
    return float(Decimal(str(ratio)) - Decimal(str(path.ratio_target)))


def rule_met(badge: Badge, metrics: Mapping[str, float | None]) -> bool:
    if badge.rule.metric not in metrics:
        raise KeyError(f"badge {badge.slug!r}: unknown metric {badge.rule.metric!r}")
    value = metrics[badge.rule.metric]
    return value is not None and value >= badge.rule.gte


def earned_badges(program: Program, metrics: BadgeMetrics, held: Iterable[str] = ()) -> list[Badge]:
    """Badges whose rule is met and that are not already held (by slug), in program order."""
    held = set(held)
    m = metrics.as_mapping()
    return [b for b in program.badges if b.slug not in held and rule_met(b, m)]
