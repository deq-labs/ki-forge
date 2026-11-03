"""Logging and completion (docs/03-program-rules.md §2).

Scores logged sets against a `BuiltSession`: per-row sets logged and on-target, per-session cleared and
all-on-target, and the full-week check. Timed or done-style work is logged as `reps = 1` against
`rep_max = 1`, so it needs no special case.

Sets are append-only: an edit is a new row whose `supersedes` points at the row it replaces. Only the
newest row in each chain counts (see `latest_sets`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

from app.rules.program import Program
from app.rules.sessions import BuiltSession, SessionItem


@dataclass(frozen=True, slots=True)
class LoggedSet:
    id: str  # client_id
    exercise: str  # slug actually performed (the swap slug in garage mode)
    reps: int | None
    logged_at: dt.datetime
    set_no: int = 0
    weight_lb: float = 0
    rir: int | None = None
    supersedes: str | None = None  # id of the row this edit replaces


@dataclass(frozen=True, slots=True)
class RowScore:
    item: SessionItem
    sets_logged: int
    on_target: bool | None  # None = not evaluated (fewer sets logged than prescribed)


@dataclass(frozen=True, slots=True)
class SessionScore:
    rows: tuple[RowScore, ...]
    sets_needed: int
    sets_logged: int
    cleared: bool
    all_on_target: bool


def latest_sets(sets: Iterable[LoggedSet]) -> list[LoggedSet]:
    """Collapse edit chains to their newest row (by `logged_at`, then id); input order is kept."""
    sets = list(sets)
    by_id = {s.id: s for s in sets}

    def root(s: LoggedSet) -> str:
        seen = {s.id}
        while s.supersedes is not None:
            parent = by_id.get(s.supersedes)
            if parent is None:
                return s.supersedes  # ancestor not in this batch; it still identifies the chain
            if parent.id in seen:
                raise ValueError(f"set edit cycle at {parent.id!r}")
            seen.add(parent.id)
            s = parent
        return s.id

    newest: dict[str, LoggedSet] = {}
    for s in sets:
        r = root(s)
        if r not in newest or (s.logged_at, s.id) > (newest[r].logged_at, newest[r].id):
            newest[r] = s
    keep = {s.id for s in newest.values()}
    return [s for s in sets if s.id in keep]


def score_row(item: SessionItem, sets: Iterable[LoggedSet]) -> RowScore:
    """Score one row against its already de-duplicated logged sets."""
    sets = list(sets)
    sets_logged = min(item.sets, len(sets))
    if sets_logged < item.sets:
        on_target = None
    elif item.is_technique:
        on_target = True  # v1: technique rows are never evaluated for target
    else:
        on_target = sum(1 for s in sets if (s.reps or 0) >= item.rep_max) >= item.sets
    return RowScore(item=item, sets_logged=sets_logged, on_target=on_target)


def score_session(session: BuiltSession, sets: Iterable[LoggedSet]) -> SessionScore:
    """Score a session. Sets for exercises not in the session are ignored; extra sets earn nothing."""
    slugs = [i.exercise for i in session.items]
    if len(set(slugs)) != len(slugs):
        raise ValueError(f"session {session.template!r} lists an exercise twice; sets cannot be matched")
    by_exercise: dict[str, list[LoggedSet]] = {slug: [] for slug in slugs}
    for s in latest_sets(sets):
        if s.exercise in by_exercise:
            by_exercise[s.exercise].append(s)

    rows = tuple(score_row(item, by_exercise[item.exercise]) for item in session.items)
    needed = sum(r.item.sets for r in rows)
    logged = sum(r.sets_logged for r in rows)
    cleared = needed > 0 and logged >= needed
    return SessionScore(
        rows=rows,
        sets_needed=needed,
        sets_logged=logged,
        cleared=cleared,
        all_on_target=cleared and all(r.on_target is not False for r in rows),
    )


def is_full_week(program: Program, cleared_templates: Iterable[str]) -> bool:
    """True when every template with `required_for_full_week` has a cleared session in the week.

    `cleared_templates` are the template codes of the week's cleared sessions (repeats are fine).
    """
    cleared = set(cleared_templates)
    return all(t.code in cleared for t in program.session_templates if t.required_for_full_week)
