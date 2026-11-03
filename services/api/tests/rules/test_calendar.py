"""Calendar: docs/03-program-rules.md section 1."""

import datetime as dt

import pytest

from app.rules.calendar import phase_display_name, phase_for, session_date, week_for
from app.rules.program import Program

START = dt.date(2026, 1, 5)  # a Monday


@pytest.mark.parametrize(
    ("date", "week"),
    [
        (dt.date(2026, 1, 5), 0),  # start Monday
        (dt.date(2026, 1, 11), 0),  # Sunday of week 0
        (dt.date(2026, 1, 12), 1),
        (dt.date(2026, 1, 4), -1),  # day before start
        (dt.date(2025, 12, 29), -1),
        (dt.date(2025, 12, 28), -2),
        (START + dt.timedelta(weeks=83, days=6), 83),
        (START + dt.timedelta(weeks=84), 84),
    ],
)
def test_week_for(date: dt.date, week: int) -> None:
    assert week_for(date, START) == week


@pytest.mark.parametrize(
    ("week", "phase", "kind"),
    [
        (0, "Trial 0", "trial"),
        (1, "Foundation", "phase"),
        (8, "Foundation", "phase"),
        (9, "Trial I", "trial"),
        (10, "Build", "phase"),
        (25, "Build", "phase"),
        (26, "Trial II", "trial"),
        (27, "Strength", "phase"),
        (38, "Strength", "phase"),
        (39, "Trial III", "trial"),
        (40, "Specialization", "phase"),
        (67, "Specialization", "phase"),
        (68, "Trial IV", "trial"),
        (69, "Reveal", "phase"),
        (82, "Reveal", "phase"),
        (83, "Final Trial", "trial"),
    ],
)
def test_phase_boundaries(program: Program, week: int, phase: str, kind: str) -> None:
    found = phase_for(week, program)
    assert found is not None
    assert (found.name, found.kind) == (phase, kind)


@pytest.mark.parametrize("week", [-52, -1, 84, 200])
def test_phase_outside_cycle(program: Program, week: int) -> None:
    assert phase_for(week, program) is None


def test_date_before_start_has_no_phase(program: Program) -> None:
    assert phase_for(week_for(dt.date(2026, 1, 1), START), program) is None


@pytest.mark.parametrize(
    ("week", "dow", "expected"),
    [
        (0, 1, dt.date(2026, 1, 5)),
        (0, 7, dt.date(2026, 1, 11)),
        (1, 1, dt.date(2026, 1, 12)),
        (1, 5, dt.date(2026, 1, 16)),
        (83, 6, START + dt.timedelta(weeks=83, days=5)),
    ],
)
def test_session_date(week: int, dow: int, expected: dt.date) -> None:
    got = session_date(START, week, dow)
    assert got == expected
    assert got.isoweekday() == dow
    assert week_for(got, START) == week


def test_session_dates_match_template_days(program: Program) -> None:
    for t in program.session_templates:
        assert session_date(START, 10, t.day_of_week).isoweekday() == t.day_of_week


@pytest.mark.parametrize("dow", [0, 8])
def test_session_date_rejects_bad_day(dow: int) -> None:
    with pytest.raises(ValueError):
        session_date(START, 0, dow)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("storm", "Storm Fighter Specialization"),
        ("shadow", "Shadow Runner Specialization"),
        ("titan", "Titan Breaker Specialization"),
        ("blade", "Blade Master Specialization"),
    ],
)
def test_specialization_display_name(program: Program, path: str, expected: str) -> None:
    assert phase_display_name(phase_for(40, program), program.path(path)) == expected


def test_other_phases_display_plain_name(program: Program) -> None:
    storm = program.path("storm")
    for ph in program.phases:
        if ph.display_name_template is None:
            assert phase_display_name(ph, storm) == ph.name
