"""Parity report: does the rules engine score a workbook exactly as the workbook does? (M1 acceptance)

Usage: python -m app.tools.parity <file.xlsx>

Compares engine output with the workbook's cached values (docs/08-testing.md, "Parity assertions"):
Log rows, Sessions rows, Weeks rows, Tests and the Start Here totals. Every mismatch is collected and
printed as one table; nothing stops at the first difference. Exit code 1 when anything differs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.rules.calendar import session_date
from app.rules.completion import score_session
from app.rules.program import Program, load_program
from app.rules.trials import FrameReading, frame_ratio, latest_frame_ratio, latest_power_level, power_level
from app.rules.trials import trial_complete as is_trial_complete
from app.rules.xp import level_progress, rank_for, session_awards
from app.tools.import_workbook import (
    TRIAL_COLUMNS,
    Workbook,
    WorkbookError,
    open_workbook,
    read_workbook,
    score_import,
)

NO_FRAME_TEXT = "Log Trial 0"  # what Start Here!F12 shows before any Trial has a ratio


@dataclass(frozen=True)
class Mismatch:
    location: str
    workbook: Any
    engine: Any
    explained: str | None = None  # set when the workbook contradicts itself and the engine matches its source

    def with_note(self, note: str) -> Mismatch:
        return Mismatch(self.location, self.workbook, self.engine, note)


@dataclass(frozen=True)
class ParityReport:
    file: str
    checked: int
    mismatches: tuple[Mismatch, ...]

    @property
    def unexplained(self) -> tuple[Mismatch, ...]:
        return tuple(m for m in self.mismatches if m.explained is None)

    @property
    def ok(self) -> bool:
        return not self.unexplained

    def table(self) -> str:
        head = (
            f"Parity: {self.file}: {self.checked} values checked, {len(self.mismatches)} mismatches "
            f"({len(self.unexplained)} unexplained)"
        )
        if not self.mismatches:
            return head
        rows = ["| Location | Workbook | Engine | Explanation |", "| --- | --- | --- | --- |"]
        rows += [
            f"| {m.location} | {_show(m.workbook)} | {_show(m.engine)} | {m.explained or '**unexplained**'} |"
            for m in self.mismatches
        ]
        return head + "\n\n" + "\n".join(rows)


def _show(v: Any) -> str:
    return "(blank)" if v is None else str(v)


def _norm(v: Any) -> Any:
    """Blank cells and "" are the same; whole floats compare as ints (Sheets writes 1.0 for 1)."""
    if v is None or v == "":
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _yes(flag: bool | None, *, no: str | None = None) -> str | None:
    """Engine bool → the workbook's text: True = "Yes", False = `no` (blank unless given), None = blank."""
    if flag is None:
        return None
    return "Yes" if flag else no


class _Checker:
    def __init__(self) -> None:
        self.checked = 0
        self.mismatches: list[Mismatch] = []

    def eq(self, location: str, workbook: Any, engine: Any) -> None:
        self.checked += 1
        w, e = _norm(workbook), _norm(engine)
        numeric = isinstance(w, int | float) and isinstance(e, int | float)
        if not (abs(w - e) < 1e-9 if numeric else w == e):
            self.mismatches.append(Mismatch(location, w, e))


def check(wb: Workbook, program: Program, file: str = "") -> ParityReport:
    data = read_workbook(wb, program)
    result = score_import(data, program)
    c = _Checker()

    # 1-2. Log rows and Sessions rows, from every block (unlogged blocks score as empty sessions).
    sessions_ws = wb.values["Sessions"]
    session_rows = {
        (_norm(sessions_ws[f"A{r}"].value), sessions_ws[f"C{r}"].value): r
        for r in range(2, sessions_ws.max_row + 1)
        if sessions_ws[f"C{r}"].value
    }
    log = wb.values["Log"]
    cleared_total = 0
    for block in data.blocks:
        score = score_session(block.built, block.sets)
        cleared_total += score.cleared
        for row, rs in zip(block.rows, score.rows, strict=True):
            r = row.row
            c.eq(f"Log!R{r} sets logged", log[f"R{r}"].value, rs.sets_logged)
            c.eq(f"Log!S{r} on target", log[f"S{r}"].value, _yes(rs.on_target, no="No"))
            c.eq(f"Log!Q{r} XP", log[f"Q{r}"].value, 5 * rs.sets_logged)
        sr = session_rows.pop((block.week, block.name), None)
        where = f"week {block.week} {block.name}"
        if sr is None:
            c.eq(f"Sessions ({where})", "missing row", "present")
            continue
        kind = program.template(block.code).kind
        xp = sum(a.amount for a in session_awards(block.client_id, kind, score) if a.type != "set_logged")
        c.eq(f"Sessions!D{sr} sets needed ({where})", sessions_ws[f"D{sr}"].value, score.sets_needed)
        c.eq(f"Sessions!E{sr} sets logged ({where})", sessions_ws[f"E{sr}"].value, score.sets_logged)
        c.eq(f"Sessions!F{sr} cleared ({where})", sessions_ws[f"F{sr}"].value, _yes(score.cleared))
        all_on = _yes(score.all_on_target, no="No") if score.cleared else None
        c.eq(f"Sessions!G{sr} all on target ({where})", sessions_ws[f"G{sr}"].value, all_on)
        c.eq(f"Sessions!H{sr} XP ({where})", sessions_ws[f"H{sr}"].value, xp)
    for (week, name), sr in session_rows.items():
        c.eq(f"Sessions!A{sr} (week {week} {name})", "present", "no Log block")

    # 3. Weeks rows.
    weeks_ws = wb.values["Weeks"]
    for r in range(2, weeks_ws.max_row + 1):
        week = _norm(weeks_ws[f"A{r}"].value)
        if not isinstance(week, int):
            continue
        full = result.full_weeks.get(week, False)
        c.eq(f"Weeks!D{r} full week (week {week})", weeks_ws[f"D{r}"].value, _yes(full))
        c.eq(f"Weeks!E{r} bonus XP (week {week})", weeks_ws[f"E{r}"].value, 150 if full else 0)

    # 4. Tests.
    tests_ws = wb.values["Tests"]
    trial_phases = [p for p in program.phases if p.is_trial]
    trial_xp = 0
    readings = []
    for col, phase in zip(TRIAL_COLUMNS, trial_phases, strict=True):
        results = data.trials[phase.ord]
        ratio = frame_ratio(results.get("shoulders_in"), results.get("waist_in"))
        complete = is_trial_complete(results, program)
        trial_xp += 500 if complete else 0
        readings.append(
            FrameReading(
                at=dt.datetime.combine(session_date(data.start_date, phase.start_week, 1), dt.time()),
                shoulders=results.get("shoulders_in"),
                waist=results.get("waist_in"),
            )
        )
        c.eq(f"Tests!{col}13 frame ratio ({phase.name})", tests_ws[f"{col}13"].value, ratio)
        c.eq(f"Tests!{col}14 Power Level ({phase.name})", tests_ws[f"{col}14"].value, power_level(results))
        c.eq(f"Tests!{col}15 complete ({phase.name})", tests_ws[f"{col}15"].value, _yes(complete))
    c.eq("Tests!C17 Trial XP", tests_ws["C17"].value, trial_xp)

    # 5. Start Here totals (the workbook has no badges or scans, so neither is in the engine's total).
    start = wb.values["Start Here"]
    xp = result.total_xp
    progress = level_progress(xp)
    ratio = latest_frame_ratio(readings)
    pl = latest_power_level(data.trials)
    c.eq("Start Here!F6 total XP", start["F6"].value, xp)
    c.eq("Start Here!F7 level", start["F7"].value, progress.level)
    c.eq("Start Here!F8 rank", start["F8"].value, rank_for(progress.level, program).name)
    c.eq("Start Here!F9 XP to next", start["F9"].value, progress.xp_to_next)
    c.eq(
        "Start Here!F12 latest frame ratio", start["F12"].value, ratio if ratio is not None else NO_FRAME_TEXT
    )
    c.eq("Start Here!F13 Power Level", start["F13"].value, pl if pl is not None else 0)
    c.eq("Start Here!F14 sessions cleared", start["F14"].value, cleared_total)

    return ParityReport(file=file, checked=c.checked, mismatches=tuple(_explain(m, wb) for m in c.mismatches))


# Start Here cells that just pick the latest Trial's value from a Tests row (LOOKUP(2,1/ISNUMBER(...))).
_LATEST_FROM_TESTS_ROW = {"Start Here!F12 latest frame ratio": 13, "Start Here!F13 Power Level": 14}


def _explain(m: Mismatch, wb: Workbook) -> Mismatch:
    """Explain a total that disagrees with the workbook's own source cells, which the engine matches.

    Such a cell's cached value was not recalculated by the app that last saved the file; the rules doc
    (latest Trial's value) and the Tests sheet agree with the engine.
    """
    row = _LATEST_FROM_TESTS_ROW.get(m.location)
    if row is None:
        return m
    tests = wb.values["Tests"]
    numeric = [_norm(tests[f"{col}{row}"].value) for col in TRIAL_COLUMNS]
    numeric = [v for v in numeric if isinstance(v, int | float)]
    if numeric and abs(numeric[-1] - m.engine) < 1e-9:
        return m.with_note(
            f"workbook disagrees with itself: Tests row {row} shows {numeric[-1]} for the latest Trial; "
            "the cached Start Here value was not recalculated. Engine follows the rules doc."
        )
    return m


def check_file(path: Path | str, program: Program | None = None) -> ParityReport:
    program = program or load_program(settings.seed_path)
    return check(open_workbook(path), program, file=Path(path).name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare the rules engine with a workbook's own results.")
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args(argv)
    try:
        report = check_file(args.workbook)
    except WorkbookError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(report.table())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
