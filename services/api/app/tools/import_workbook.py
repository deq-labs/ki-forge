"""Read Joe's Ki Forge Excel workbook into rules-engine inputs (dry run; no DB writes in M1).

Usage: python -m app.tools.import_workbook <file.xlsx>

Layout and mapping: docs/08-testing.md. The workbook is read twice: once with `data_only=True` for the
cached values Excel computed (the parity oracle), once normally to confirm the formulas are intact.
Log rows map to prescriptions by position within their (week, session) block, never by name.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import sys
import uuid
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from app.config import settings
from app.rules.calendar import phase_for, session_date
from app.rules.completion import LoggedSet, SessionScore, is_full_week, score_session
from app.rules.program import Program, load_program
from app.rules.sessions import BuiltSession, build_session
from app.rules.trials import TestResults, latest_power_level, trial_awards
from app.rules.xp import Award, full_week_award, level_progress, rank_for, session_awards, total_xp

# Fixed namespace so ids are identical on every import of the same workbook.
IMPORT_NS = uuid.UUID("5f0c7e3a-2b8d-4f61-9a57-0d3c1e9b7a42")

LOG_FIRST_ROW = 2
SET_COLUMNS = ("K", "L", "M", "N")
# Workbook layout: Tests rows 3-11, in this order; columns C-H are the Trials in phase order.
TEST_ROWS = (
    (3, "pullups_max"),
    (4, "pushups_max"),
    (5, "row_2k_seconds"),
    (6, "press_5rm_lb"),
    (7, "squat_5rm_lb"),
    (8, "deadlift_5rm_lb"),
    (9, "bodyweight_lb"),
    (10, "shoulders_in"),
    (11, "waist_in"),
)
TRIAL_COLUMNS = ("C", "D", "E", "F", "G", "H")
# Formula cells that must still be formulas for the cached values to mean anything.
REQUIRED_FORMULAS = (
    ("Start Here", "F6"),
    ("Start Here", "F7"),
    ("Tests", "C14"),
    ("Log", "Q2"),
    ("Log", "R2"),
)


class WorkbookError(ValueError):
    """The workbook can't be imported (wrong layout, broken formulas)."""


class MissingCachedValues(WorkbookError):
    """The file has formulas but no cached results: it was never opened and saved in Excel or Sheets."""


@dataclass(frozen=True)
class ImportedRow:
    row: int  # Log sheet row number
    position: int  # index within the session block, = index into BuiltSession.items
    garage: bool
    sets: tuple[LoggedSet, ...]


@dataclass(frozen=True)
class ImportedSession:
    client_id: str
    week: int
    code: str  # template code
    name: str  # session name as the workbook writes it, e.g. "Upper A"
    date: dt.date
    garage_mode: bool
    built: BuiltSession  # per row: the garage item if that row is P = "Y", else the gym item
    rows: tuple[ImportedRow, ...]  # every Log row of the block, logged or not

    @property
    def sets(self) -> list[LoggedSet]:
        return [s for r in self.rows for s in r.sets]


@dataclass(frozen=True)
class WorkbookImport:
    enrollment_id: str
    start_date: dt.date
    path: str  # path slug
    bodyweight_lb: float | None
    blocks: tuple[ImportedSession, ...]  # every (week, session) block in the Log, logged or not
    trials: Mapping[int, TestResults]  # by phase ord
    warnings: tuple[str, ...] = ()

    @property
    def sessions(self) -> tuple[ImportedSession, ...]:
        """Blocks with at least one logged set: the sessions an import creates."""
        return tuple(b for b in self.blocks if b.sets)


@dataclass(frozen=True)
class Workbook:
    """Both views of the file: `values` holds cached results, `formulas` the formula text."""

    values: openpyxl.Workbook
    formulas: openpyxl.Workbook


def has_cached_values(wb: Workbook) -> bool:
    return wb.values["Start Here"]["F6"].value is not None and wb.values["Log"]["R2"].value is not None


def open_workbook(source: Path | str | bytes, *, require_cached: bool = True) -> Workbook:
    """Open a workbook from a path or the uploaded bytes.

    `require_cached=False` allows a file without cached formula results (e.g. one written by a script):
    it can still be imported, but there is nothing to compare parity against.
    """

    def load(data_only: bool) -> openpyxl.Workbook:
        src = io.BytesIO(source) if isinstance(source, bytes) else source
        try:
            return openpyxl.load_workbook(src, data_only=data_only)
        except (zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
            raise WorkbookError(f"not a readable .xlsx workbook ({exc})") from exc

    values, formulas = load(True), load(False)
    for sheet in ("Start Here", "Log", "Tests", "Sessions", "Weeks"):
        if sheet not in values.sheetnames:
            raise WorkbookError(f"missing sheet {sheet!r}")
    for sheet, cell in REQUIRED_FORMULAS:
        f = formulas[sheet][cell].value
        if not (isinstance(f, str) and f.startswith("=")):
            raise WorkbookError(f"{sheet}!{cell} should be a formula but is {f!r}; formulas were overwritten")
    wb = Workbook(values=values, formulas=formulas)
    if require_cached and not has_cached_values(wb):
        raise MissingCachedValues(
            "the workbook has no cached formula results; open it in Excel or Google Sheets, save it once, "
            "and import again"
        )
    return wb


def _number(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    return v


def _int_or_float(v: float) -> int | float:
    return int(v) if float(v).is_integer() else v


def _date(v: Any, where: str) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    raise WorkbookError(f"{where}: expected a date, got {v!r}")


def _id(*parts: object) -> str:
    return str(uuid.uuid5(IMPORT_NS, ":".join(str(p) for p in parts)))


def session_client_id(start_date: dt.date, week: int, session_name: str) -> str:
    """UUID5 of "{start_date}:{week}:{session}" (docs/08-testing.md)."""
    return str(uuid.uuid5(IMPORT_NS, f"{start_date.isoformat()}:{week}:{session_name}"))


def _log_blocks(ws: Worksheet) -> list[tuple[int, str, list[int]]]:
    """(week, session name, [row numbers]) for each consecutive block of Log rows."""
    blocks: list[tuple[int, str, list[int]]] = []
    for r in range(LOG_FIRST_ROW, ws.max_row + 1):
        week, name = ws[f"A{r}"].value, ws[f"D{r}"].value
        if week is None and name is None:
            continue
        if isinstance(week, float) and week.is_integer():
            week = int(week)  # Google Sheets saves whole numbers as floats
        if isinstance(week, bool) or not isinstance(week, int) or not isinstance(name, str):
            raise WorkbookError(
                f"Log!A{r}:D{r}: expected a week number and session name, got {week!r}, {name!r}"
            )
        if blocks and blocks[-1][0] == week and blocks[-1][1] == name:
            blocks[-1][2].append(r)
        else:
            blocks.append((week, name, [r]))
    return blocks


def read_workbook(wb: Workbook, program: Program) -> WorkbookImport:
    start_ws = wb.values["Start Here"]
    start_date = _date(start_ws["C6"].value, "Start Here!C6")
    path_name = start_ws["C7"].value
    by_name = {p.name: p for p in program.paths.values()}
    if path_name not in by_name:
        raise WorkbookError(f"Start Here!C7: unknown path {path_name!r}; expected one of {sorted(by_name)}")
    path = by_name[path_name]
    bodyweight = _number(start_ws["C8"].value)
    templates = {t.short: t for t in program.session_templates}
    warnings: list[str] = []

    log = wb.values["Log"]
    sessions: list[ImportedSession] = []
    seen: set[tuple[int, str]] = set()
    for week, name, rows in _log_blocks(log):
        if name not in templates:
            raise WorkbookError(f"Log!D{rows[0]}: unknown session {name!r}")
        if (week, name) in seen:
            raise WorkbookError(f"Log!D{rows[0]}: week {week} {name} appears twice")
        seen.add((week, name))
        template = templates[name]
        phase = phase_for(week, program)
        if phase is None:
            raise WorkbookError(f"Log!A{rows[0]}: week {week} is outside the program")
        gym = build_session(program, template, phase, path, garage_mode=False)
        garage = build_session(program, template, phase, path, garage_mode=True)
        if len(rows) != len(gym.items):
            raise WorkbookError(
                f"Log rows {rows[0]}-{rows[-1]} ({name}, week {week}): {len(rows)} rows but the program has "
                f"{len(gym.items)} exercises"
            )

        cid = session_client_id(start_date, week, name)
        day = session_date(start_date, week, template.day_of_week)
        logged_at = dt.datetime.combine(day, dt.time(12))
        imported_rows: list[ImportedRow] = []
        items = []
        for pos, r in enumerate(rows):
            is_garage = str(log[f"P{r}"].value or "").strip().upper() == "Y"
            item = garage.items[pos] if is_garage else gym.items[pos]
            items.append(item)
            prescribed = _number(log[f"H{r}"].value)
            if prescribed is not None and prescribed != item.sets:
                warnings.append(f"Log!H{r}: workbook prescribes {prescribed:g} sets, program has {item.sets}")
            weight = _number(log[f"J{r}"].value) or 0
            rir = _number(log[f"O{r}"].value)
            sets = []
            for n, col in enumerate(SET_COLUMNS, 1):
                reps = _number(log[f"{col}{r}"].value)
                if reps is None:
                    continue
                sets.append(
                    LoggedSet(
                        id=_id(cid, pos, n),
                        exercise=item.exercise,
                        reps=int(reps),
                        logged_at=logged_at,
                        set_no=n,
                        weight_lb=weight,
                        rir=int(rir) if rir is not None else None,
                    )
                )
            imported_rows.append(ImportedRow(row=r, position=pos, garage=is_garage, sets=tuple(sets)))

        sessions.append(
            ImportedSession(
                client_id=cid,
                week=week,
                code=template.code,
                name=name,
                date=day,
                garage_mode=any(r.garage for r in imported_rows),
                built=BuiltSession(template=template.code, items=tuple(items)),
                rows=tuple(imported_rows),
            )
        )

    tests = wb.values["Tests"]
    trial_phases = [p for p in program.phases if p.is_trial]
    if len(trial_phases) != len(TRIAL_COLUMNS):
        raise WorkbookError(f"program has {len(trial_phases)} Trials; the workbook has {len(TRIAL_COLUMNS)}")
    known = {t.type for t in program.tests}
    if {t for _, t in TEST_ROWS} != known:
        raise WorkbookError(
            f"workbook tests {sorted(t for _, t in TEST_ROWS)} differ from program {sorted(known)}"
        )
    trials: dict[int, TestResults] = {}
    for col, phase in zip(TRIAL_COLUMNS, trial_phases, strict=True):
        results = {}
        for row, test_type in TEST_ROWS:
            v = _number(tests[f"{col}{row}"].value)
            results[test_type] = _int_or_float(v) if v is not None else None
        trials[phase.ord] = results

    return WorkbookImport(
        enrollment_id=_id("enrollment", start_date.isoformat()),
        start_date=start_date,
        path=path.slug,
        bodyweight_lb=bodyweight,
        blocks=tuple(sessions),
        trials=trials,
        warnings=tuple(warnings),
    )


# --- scoring (what the server would compute from the import) --------------------------------------------


@dataclass
class ImportResult:
    data: WorkbookImport
    scores: dict[str, SessionScore] = field(default_factory=dict)  # by session client_id
    awards: list[Award] = field(default_factory=list)
    full_weeks: dict[int, bool] = field(default_factory=dict)

    @property
    def total_xp(self) -> int:
        return total_xp(self.awards)


def score_import(data: WorkbookImport, program: Program) -> ImportResult:
    result = ImportResult(data=data)
    cleared_by_week: dict[int, list[str]] = {}
    for s in data.sessions:
        score = score_session(s.built, s.sets)
        result.scores[s.client_id] = score
        result.awards += session_awards(s.client_id, program.template(s.code).kind, score)
        cleared_by_week.setdefault(s.week, [])
        if score.cleared:
            cleared_by_week[s.week].append(s.code)
    for week, cleared in sorted(cleared_by_week.items()):
        result.full_weeks[week] = is_full_week(program, cleared)
        if result.full_weeks[week]:
            result.awards.append(full_week_award(data.enrollment_id, week))
    for ord_, results in data.trials.items():
        result.awards += trial_awards(data.enrollment_id, ord_, results, program)
    return result


def summary(result: ImportResult, program: Program) -> str:
    data = result.data
    xp = result.total_xp
    progress = level_progress(xp)
    pl = latest_power_level(data.trials)
    lines = [
        f"start date      {data.start_date.isoformat()}",
        f"path            {program.path(data.path).name}",
        f"sessions        {len(data.sessions)} ({sum(s.cleared for s in result.scores.values())} cleared)",
        f"sets            {sum(len(s.sets) for s in data.sessions)}",
        f"full weeks      {sum(result.full_weeks.values())}",
        f"trials entered  {sum(1 for t in data.trials.values() if any(v is not None for v in t.values()))}",
        f"total XP        {xp}",
        f"level           {progress.level} ({rank_for(progress.level, program).name}), "
        f"{progress.xp_to_next} XP to next",
        f"power level     {pl if pl is not None else '-'}",
    ]
    lines += [f"warning: {w}" for w in data.warnings]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run import of a Ki Forge workbook.")
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args(argv)
    program = load_program(settings.seed_path)
    try:
        data = read_workbook(open_workbook(args.workbook), program)
    except WorkbookError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(summary(score_import(data, program), program))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
