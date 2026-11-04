"""Progression: the pre-filled weight for an exercise's next session (docs/03-program-rules.md §5).

Double progression per exercise per user, keyed by the exercise actually performed, so garage swaps
track their own progression separately from the exercise they replace.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from app.rules.completion import LoggedSet, latest_sets
from app.rules.program import Phase, Program
from app.rules.sessions import BuiltSession, SessionItem

STALL_LIMIT = 3  # main-lift sessions in a row without progress before the drop
STALL_DROP = Decimal("0.9")


@dataclass(frozen=True, slots=True)
class ProgressionState:
    next_weight_lb: float
    stall_count: int = 0


def round_down(weight: float, increment: float) -> float:
    """Largest multiple of `increment` at or below `weight` (exact decimal math)."""
    inc = Decimal(str(increment))
    if inc <= 0:
        return weight
    return float((Decimal(str(weight)) / inc).to_integral_value(rounding=ROUND_FLOOR) * inc)


def target_rir(phase: Phase, is_main_lift: bool) -> int | None:
    """The phase's RIR target; for the main lift a `main_lift_rir` range applies (its upper end)."""
    rir_range = phase.modifiers.main_lift_rir
    if is_main_lift and rir_range:
        return max(rir_range)
    return phase.rir_target


def hit_target(item: SessionItem, sets: Sequence[LoggedSet], phase: Phase) -> bool:
    """Every prescribed set reached `rep_max` at or below the target RIR (missing RIR counts as on target)."""
    counted = sorted(sets, key=lambda s: (s.logged_at, s.set_no, s.id))[: item.sets]
    if len(counted) < item.sets:
        return False
    rir = target_rir(phase, item.is_main_lift)
    return all(
        (s.reps or 0) >= item.rep_max and (s.rir is None or rir is None or s.rir <= rir) for s in counted
    )


def progress(
    state: ProgressionState | None,
    item: SessionItem,
    sets: Sequence[LoggedSet],
    phase: Phase,
    increment_lb: float,
) -> ProgressionState:
    """New state after one session of this exercise. `sets` must be the latest rows for the exercise."""
    if not sets:
        raise ValueError(f"no sets logged for {item.exercise!r}")
    last_weight = max(s.weight_lb for s in sets)
    stall = state.stall_count if state else 0

    if phase.modifiers.progression == "hold_weights":
        return ProgressionState(next_weight_lb=last_weight, stall_count=stall)
    if hit_target(item, sets, phase):
        return ProgressionState(next_weight_lb=last_weight + increment_lb, stall_count=0)
    if not item.is_main_lift:
        return ProgressionState(next_weight_lb=last_weight, stall_count=0)
    stall += 1
    if stall >= STALL_LIMIT:
        dropped = round_down(float(Decimal(str(last_weight)) * STALL_DROP), increment_lb)
        return ProgressionState(next_weight_lb=dropped, stall_count=0)
    return ProgressionState(next_weight_lb=last_weight, stall_count=stall)


def progress_session(
    program: Program,
    phase: Phase,
    session: BuiltSession,
    sets: Iterable[LoggedSet],
    states: Mapping[str, ProgressionState],
) -> dict[str, ProgressionState]:
    """Updated states for every exercise in the session that has logged sets; others are untouched."""
    by_exercise: dict[str, list[LoggedSet]] = {}
    for s in latest_sets(sets):
        by_exercise.setdefault(s.exercise, []).append(s)
    out = dict(states)
    for item in session.items:
        # A swapped row may have been done as written, a technique on any of its steps; each exercise
        # performed keeps its own state.
        for slug in (item.exercise, item.replaces, *item.alternatives):
            logged = by_exercise.get(slug) if slug else None
            if logged:
                out[slug] = progress(
                    states.get(slug), item, logged, phase, program.exercise(slug).increment_lb
                )
    return out
