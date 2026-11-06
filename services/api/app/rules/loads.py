"""Loads from a percent of 1RM (docs/03-program-rules.md, EMOM path).

`percent_load(percent, one_rm_lb, increment_lb)` is the working weight shown for a target such as
"3 @ 80%": the 1RM times the percent, rounded to the nearest loadable increment (half rounds up).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def percent_load(percent: float, one_rm_lb: float, increment_lb: float = 5) -> float:
    """`percent`% of `one_rm_lb`, rounded to the nearest `increment_lb` (e.g. 80% of 305 → 245)."""
    if one_rm_lb <= 0 or percent <= 0:
        return 0.0
    raw = Decimal(str(one_rm_lb)) * Decimal(str(percent)) / 100
    if increment_lb <= 0:
        return float(raw)
    inc = Decimal(str(increment_lb))
    return float((raw / inc).quantize(Decimal(1), rounding=ROUND_HALF_UP) * inc)
