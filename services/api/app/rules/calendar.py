"""Training calendar (docs/03-program-rules.md §1).

An enrollment's `start_date` is the Monday of the Trial 0 week. Week numbers are relative to it:
week 0 is Trial 0, negative weeks are before the program starts.
"""

from __future__ import annotations

import datetime as dt

from app.rules.program import Phase, Program, TrainingPath


def week_for(date: dt.date, start_date: dt.date) -> int:
    """`floor((date - start_date).days / 7)`; negative before the start date."""
    return (date - start_date).days // 7


def phase_for(week: int, program: Program) -> Phase | None:
    """The phase whose `start_week <= week <= end_week`, or None outside the cycle (e.g. before start)."""
    for phase in program.phases:
        if phase.contains(week):
            return phase
    return None


def session_date(start_date: dt.date, week: int, day_of_week: int) -> dt.date:
    """Suggested date of a session: `start_date + 7 * week + (day_of_week - 1)`, ISO Monday = 1."""
    if not 1 <= day_of_week <= 7:
        raise ValueError(f"day_of_week must be 1..7 (ISO), got {day_of_week}")
    return start_date + dt.timedelta(days=7 * week + day_of_week - 1)


def phase_display_name(phase: Phase, path: TrainingPath) -> str:
    """Phase name as shown to the user; e.g. Specialization becomes "Storm Fighter Specialization"."""
    if phase.display_name_template:
        return phase.display_name_template.format(path=path.name)
    return phase.name
