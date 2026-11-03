"""Workbook importer (dry run): docs/08-testing.md, "Import mapping"."""

from pathlib import Path

import openpyxl
import pytest

from app.config import REPO_ROOT
from app.rules.program import Program
from app.tools.import_workbook import (
    MissingCachedValues,
    Workbook,
    WorkbookError,
    main,
    open_workbook,
    read_workbook,
    score_import,
    session_client_id,
)

TEMPLATE = REPO_ROOT / "fixtures" / "Ki_Forge_Training_Log_TEMPLATE.xlsx"
UPPER_A_W1 = range(2, 10)  # Log rows 2-9: six prescriptions + two path technique rows


@pytest.fixture
def wb() -> Workbook:
    return open_workbook(TEMPLATE)


def fill(wb: Workbook, cells: dict[str, object]) -> None:
    """Enter inputs into the in-memory Log sheet (both views, as Excel would after a save)."""
    for ref, value in cells.items():
        wb.values["Log"][ref] = value
        wb.formulas["Log"][ref] = value


def upper_a_at_top(wb: Workbook) -> None:
    log = wb.values["Log"]
    for r in UPPER_A_W1:
        sets, top = log[f"H{r}"].value, log[f"I{r}"].value or 12
        fill(wb, {f"J{r}": 50, **{f"{c}{r}": top for c in "KLMN"[:sets]}})


def test_template_imports_zero_sessions_and_zero_xp(program: Program, wb: Workbook) -> None:
    data = read_workbook(wb, program)
    assert (data.path, data.start_date.isoformat()) == ("storm", "2026-10-26")
    assert data.sessions == ()
    assert data.warnings == ()
    assert all(v is None for t in data.trials.values() for v in t.values())
    assert sorted(data.trials) == [0, 2, 4, 6, 8, 10]
    assert score_import(data, program).total_xp == 0


def test_reimport_is_identical(program: Program) -> None:
    def load():
        w = open_workbook(TEMPLATE)
        upper_a_at_top(w)
        return read_workbook(w, program)

    a, b = load(), load()
    assert a == b
    assert a.sessions[0].client_id == session_client_id(a.start_date, 1, "Upper A")
    assert len({s.id for s in a.sessions[0].sets}) == 23


def test_filled_upper_a_scores_golden_240(program: Program, wb: Workbook) -> None:
    upper_a_at_top(wb)
    data = read_workbook(wb, program)
    (session,) = data.sessions
    assert (session.week, session.code, session.date.isoformat(), session.garage_mode) == (
        1,
        "upper_a",
        "2026-11-02",
        False,
    )
    assert len(session.sets) == 23
    assert all(s.weight_lb == 50 for s in session.sets)
    result = score_import(data, program)
    assert result.scores[session.client_id].cleared
    assert result.total_xp == 240


def test_rows_map_by_position_not_name(program: Program, wb: Workbook) -> None:
    fill(wb, {"E2": "Something renamed", "K2": 10})
    (session,) = read_workbook(wb, program).sessions
    assert session.sets[0].exercise == "standing-barbell-overhead-press"


def test_garage_rows_use_swap_exercise(program: Program, wb: Workbook) -> None:
    upper_a_at_top(wb)
    fill(wb, {"P2": "Y"})
    (session,) = read_workbook(wb, program).sessions
    assert session.garage_mode
    assert session.rows[0].garage and not session.rows[1].garage
    assert {s.exercise for s in session.rows[0].sets} == {"dumbbell-standing-press"}
    assert session.built.items[0].is_swap and not session.built.items[1].is_swap
    assert score_import(read_workbook(wb, program), program).total_xp == 240


def test_zero_reps_counts_as_logged(program: Program, wb: Workbook) -> None:
    fill(wb, {"K15": 0})  # Engine row: COUNT() in the workbook counts a 0
    (session,) = read_workbook(wb, program).sessions
    result = score_import(read_workbook(wb, program), program)
    assert (session.code, len(session.sets)) == ("engine", 1)
    assert result.scores[session.client_id].cleared


def test_rir_and_trials_are_read(program: Program, wb: Workbook) -> None:
    fill(wb, {"K15": 1, "O15": 2})
    golden = (8, 30, 510, 115, 185, 245, 190, 45.5, 34)
    for row, v in zip(range(3, 12), golden, strict=True):
        wb.values["Tests"][f"C{row}"] = v
    data = read_workbook(wb, program)
    assert data.sessions[0].sets[0].rir == 2
    assert data.trials[0]["shoulders_in"] == 45.5
    assert score_import(data, program).total_xp == 5 + 50 + 500


def test_missing_cached_values_is_reported(tmp_path: Path) -> None:
    copy = tmp_path / "resaved.xlsx"
    openpyxl.load_workbook(TEMPLATE).save(copy)  # openpyxl keeps formulas but drops cached results
    with pytest.raises(MissingCachedValues, match="open it in Excel"):
        open_workbook(copy)


def test_overwritten_formulas_are_rejected(tmp_path: Path) -> None:
    broken = openpyxl.load_workbook(TEMPLATE)
    broken["Start Here"]["F6"] = 123
    copy = tmp_path / "broken.xlsx"
    broken.save(copy)
    with pytest.raises(WorkbookError, match="formulas were overwritten"):
        open_workbook(copy)


def test_whole_number_floats_from_sheets(program: Program, wb: Workbook) -> None:
    for r in UPPER_A_W1:
        wb.values["Log"][f"A{r}"] = 1.0  # Google Sheets saves numbers as floats
    fill(wb, {"K2": 10.0})
    (session,) = read_workbook(wb, program).sessions
    assert (session.week, session.sets[0].reps) == (1, 10)


def test_unknown_path_is_rejected(program: Program, wb: Workbook) -> None:
    wb.values["Start Here"]["C7"] = "Mystery Path"
    with pytest.raises(WorkbookError, match="unknown path"):
        read_workbook(wb, program)


def test_cli_on_template(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(TEMPLATE)]) == 0
    out = capsys.readouterr().out
    assert "sessions        0" in out
    assert "total XP        0" in out
