"""Synthetic fixtures built in code (docs/08-testing.md, "Synthetic fixtures").

`log_session` / `log_week` produce built sessions plus logged sets; `run_week` scores them the way the
server will (completion, awards, full week, progression).
"""

from __future__ import annotations

import datetime as dt
import itertools
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from app.rules.calendar import phase_for, session_date
from app.rules.completion import LoggedSet, SessionScore, is_full_week, score_session
from app.rules.program import Phase, Program
from app.rules.progression import ProgressionState, progress_session
from app.rules.sessions import BuiltSession, build_session
from app.rules.xp import Award, full_week_award, session_awards, total_xp

START = dt.date(2026, 1, 5)  # Monday of Trial 0
ENROLLMENT = "enr-synthetic"
_ids = itertools.count()


@dataclass(frozen=True)
class SessionLog:
    session_id: str
    code: str
    kind: str
    phase: Phase
    built: BuiltSession
    sets: list[LoggedSet]
    garage: bool


def log_session(
    program: Program,
    code: str,
    week: int,
    *,
    path: str = "storm",
    garage: bool = False,
    short: int = 0,
    reps: Callable[[str, int], int] | None = None,  # (exercise, rep_max) -> reps; default top reps
    weight: Callable[[str], float] = lambda _: 100.0,
    rir: int | None = None,
    session_id: str | None = None,
) -> SessionLog:
    template = program.template(code)
    phase = phase_for(week, program)
    built = build_session(program, template, phase, program.path(path), garage_mode=garage)
    day = session_date(START, week, template.day_of_week)
    at = dt.datetime(day.year, day.month, day.day, 6, tzinfo=dt.UTC)
    sets: list[LoggedSet] = []
    for item in built.items:
        for n in range(1, item.sets + 1):
            sets.append(
                LoggedSet(
                    id=f"set-{next(_ids)}",
                    exercise=item.exercise,
                    reps=reps(item.exercise, item.rep_max) if reps else item.rep_max,
                    logged_at=at + dt.timedelta(minutes=len(sets)),
                    set_no=n,
                    weight_lb=weight(item.exercise),
                    rir=rir,
                )
            )
    if short:
        sets = sets[:-short]
    return SessionLog(
        session_id=session_id or f"sess-{code}-w{week}-{next(_ids)}",
        code=code,
        kind=template.kind,
        phase=phase,
        built=built,
        sets=sets,
        garage=garage,
    )


def log_week(program: Program, week: int, *, short_code: str | None = None, **kwargs) -> list[SessionLog]:
    """All six sessions of a week; `short_code` logs that session one set short."""
    return [
        log_session(program, t.code, week, short=1 if t.code == short_code else 0, **kwargs)
        for t in program.session_templates
    ]


@dataclass
class WeekResult:
    scores: dict[str, SessionScore]
    awards: list[Award]
    full_week: bool
    states: dict[str, ProgressionState] = field(default_factory=dict)

    @property
    def xp(self) -> int:
        return total_xp(self.awards)

    @property
    def cleared(self) -> list[str]:
        return [code for code, s in self.scores.items() if s.cleared]


def run_week(
    program: Program, week: int, logs: list[SessionLog], states: Mapping[str, ProgressionState] | None = None
) -> WeekResult:
    scores: dict[str, SessionScore] = {}
    awards: list[Award] = []
    out_states = dict(states or {})
    for log in logs:
        score = score_session(log.built, log.sets)
        scores[log.code] = score
        awards += session_awards(log.session_id, log.kind, score)
        out_states = progress_session(program, log.phase, log.built, log.sets, out_states)
    full = is_full_week(program, [c for c, s in scores.items() if s.cleared])
    if full:
        awards.append(full_week_award(ENROLLMENT, week))
    return WeekResult(scores=scores, awards=awards, full_week=full, states=out_states)
