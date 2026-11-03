"""Trials, frame ratio and Power Level (docs/03-program-rules.md §4).

A Trial is a set of test results keyed by test type (`program.tests[*].type`). A test is "entered"
when its value is not None. Rounding is half away from zero, matching Excel's ROUND, not Python's
banker's rounding.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.rules.program import Program, TrainingPath
from app.rules.xp import Award, trial_award

# Test types the Power Level formula reads (they are defined in program.json `tests`).
PULLUPS = "pullups_max"
PUSHUPS = "pushups_max"
ROW_2K = "row_2k_seconds"
PRESS_5RM = "press_5rm_lb"
SQUAT_5RM = "squat_5rm_lb"
DEADLIFT_5RM = "deadlift_5rm_lb"
SHOULDERS = "shoulders_in"
WAIST = "waist_in"

ROW_PAR_SECONDS = 540  # 9:00 for 2,000 m; faster earns 1 point per second

TestResults = Mapping[str, float | None]


def _round_half_up(x: Decimal, places: int = 0) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _dec(x: float) -> Decimal:
    return Decimal(str(x))  # exact decimal of the number as written, not its binary float


def frame_ratio(shoulders: float | None, waist: float | None) -> float | None:
    """`round(shoulders / waist, 2)` when both are > 0, else None."""
    if not shoulders or not waist or shoulders <= 0 or waist <= 0:
        return None
    return float(_round_half_up(_dec(shoulders) / _dec(waist), 2))


def _value(results: TestResults, test: str) -> float:
    v = results.get(test)
    return v if v is not None else 0


def entered(results: TestResults) -> set[str]:
    return {k for k, v in results.items() if v is not None}


def power_level(results: TestResults) -> int | None:
    """Power Level for one Trial; None when no tests are entered."""
    if not entered(results):
        return None
    row = _value(results, ROW_2K)
    ratio = frame_ratio(results.get(SHOULDERS), results.get(WAIST))
    return (
        math.floor(_value(results, PRESS_5RM) / 5)
        + math.floor(_value(results, SQUAT_5RM) / 5)
        + math.floor(_value(results, DEADLIFT_5RM) / 5)
        + 5 * int(_value(results, PULLUPS))
        + int(_value(results, PUSHUPS))
        + (max(0, ROW_PAR_SECONDS - int(row)) if row > 0 else 0)
        + (int(_round_half_up((_dec(ratio) - 1) * 1000)) if ratio is not None else 0)
    )


def trial_complete(results: TestResults, program: Program) -> bool:
    """All of the program's tests are entered for this Trial."""
    return {t.type for t in program.tests} <= entered(results)


def trial_awards(enrollment_id: str, phase_ord: int, results: TestResults, program: Program) -> list[Award]:
    """500 XP once the Trial is complete; a partial Trial awards nothing."""
    return [trial_award(enrollment_id, phase_ord)] if trial_complete(results, program) else []


def latest_power_level(trials: Mapping[int, TestResults]) -> int | None:
    """Power Level of the latest Trial (highest phase ord) that has any tests entered."""
    for ord_ in sorted(trials, reverse=True):
        pl = power_level(trials[ord_])
        if pl is not None:
            return pl
    return None


@dataclass(frozen=True, slots=True)
class FrameReading:
    """A tape measurement from a Trial or a progress scan."""

    at: dt.datetime
    shoulders: float | None
    waist: float | None

    @property
    def ratio(self) -> float | None:
        return frame_ratio(self.shoulders, self.waist)


def latest_frame_ratio(readings: Iterable[FrameReading]) -> float | None:
    """Ratio of the most recent reading that has one, from Trials or scans."""
    valid = [r for r in readings if r.ratio is not None]
    return max(valid, key=lambda r: r.at).ratio if valid else None


def meets_frame_target(ratio: float | None, path: TrainingPath) -> bool:
    return ratio is not None and ratio >= path.ratio_target
