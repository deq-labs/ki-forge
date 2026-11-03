"""Parity: the engine scores each workbook in fixtures/ exactly as the workbook does (M1 acceptance)."""

from pathlib import Path

import pytest

from app.config import REPO_ROOT
from app.rules.program import Program
from app.tools.import_workbook import open_workbook
from app.tools.parity import Mismatch, ParityReport, check, check_file, main

FIXTURES = REPO_ROOT / "fixtures"
TEMPLATE = FIXTURES / "Ki_Forge_Training_Log_TEMPLATE.xlsx"
PERSONAL = sorted(FIXTURES.glob("joe_*.xlsx"))  # gitignored; CI skips


def test_template_full_parity(program: Program) -> None:
    report = check_file(TEMPLATE, program)
    assert report.mismatches == (), report.table()
    assert report.checked > 1_000  # 240 Log rows x 3 + 48 sessions x 5 + 8 weeks x 2 + tests + totals


@pytest.mark.skipif(not PERSONAL, reason="no fixtures/joe_*.xlsx (personal workbook is gitignored)")
@pytest.mark.parametrize("path", PERSONAL, ids=[p.name for p in PERSONAL])
def test_personal_workbook_parity(program: Program, path: Path) -> None:
    report = check_file(path, program)
    print(report.table())
    assert report.ok, report.table()


def test_mismatches_are_all_reported_not_just_the_first(program: Program) -> None:
    wb = open_workbook(TEMPLATE)
    wb.values["Start Here"]["F6"] = 999
    wb.values["Log"]["R2"] = 3
    wb.values["Sessions"]["D2"] = 22
    report = check(wb, program)
    locations = {m.location for m in report.mismatches}
    assert {
        "Start Here!F6 total XP",
        "Log!R2 sets logged",
        "Sessions!D2 sets needed (week 1 Upper A)",
    } <= locations
    assert not report.ok
    assert "| Log!R2 sets logged | 3 | 0 | **unexplained** |" in report.table()


def test_engine_matches_a_filled_session(program: Program) -> None:
    # Fill W1 Upper A at top reps and set the cached values Excel would compute.
    wb = open_workbook(TEMPLATE)
    log = wb.values["Log"]
    for r in range(2, 10):
        sets, top = log[f"H{r}"].value, log[f"I{r}"].value
        for col in "KLMN"[:sets]:
            log[f"{col}{r}"] = top or 12
        log[f"R{r}"], log[f"Q{r}"], log[f"S{r}"] = sets, 5 * sets, "Yes"
    s = wb.values["Sessions"]
    s["E2"], s["F2"], s["G2"], s["H2"] = 23, "Yes", "Yes", 125
    start = wb.values["Start Here"]
    start["F6"], start["F9"], start["F14"] = 240, 160, 1
    report = check(wb, program)
    assert report.mismatches == (), report.table()


def test_stale_latest_trial_total_is_explained(program: Program) -> None:
    wb = open_workbook(TEMPLATE)
    trial0 = (8, 25, 600, 75, 165, 205, 182, None, None)  # a partial Trial 0, Power Level 154
    for row, v in zip(range(3, 12), trial0, strict=True):
        wb.values["Tests"][f"C{row}"] = v
    wb.values["Tests"]["C14"] = 154  # the workbook's own Trial value is right ...
    report = check(wb, program)  # ... but Start Here!F13 still caches 0
    (m,) = report.mismatches
    assert (m.location, m.workbook, m.engine) == ("Start Here!F13 Power Level", 0, 154)
    assert m.explained and report.ok


def test_explanation_requires_the_workbook_source_to_agree(program: Program) -> None:
    wb = open_workbook(TEMPLATE)
    wb.values["Tests"]["C3"] = 8  # engine: 40; workbook's Tests row 14 left blank
    report = check(wb, program)
    assert any(m.location.startswith("Tests!C14") for m in report.unexplained)
    assert not report.ok


def test_report_table_format() -> None:
    r = ParityReport("x.xlsx", 3, (Mismatch("A1", 1, 2), Mismatch("B2", None, "x", "because")))
    assert r.table().splitlines()[0] == "Parity: x.xlsx: 3 values checked, 2 mismatches (1 unexplained)"
    assert "| B2 | (blank) | x | because |" in r.table()


def test_cli_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(TEMPLATE)]) == 0
    assert "0 mismatches" in capsys.readouterr().out
