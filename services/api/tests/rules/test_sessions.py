"""Session builder: docs/03-program-rules.md section 1, "Building a session for a given week"."""

import pytest

from app.rules.calendar import phase_for
from app.rules.program import Program
from app.rules.sessions import BuiltSession, build_session

FOUNDATION, BUILD, STRENGTH, SPECIALIZATION, REVEAL = 1, 10, 27, 40, 69  # first week of each phase


def build(program: Program, code: str, week: int, path: str = "storm", garage: bool = False) -> BuiltSession:
    return build_session(
        program, program.template(code), phase_for(week, program), program.path(path), garage_mode=garage
    )


def item(session: BuiltSession, slug: str):
    (found,) = [i for i in session.items if i.exercise == slug]
    return found


def test_golden_foundation_week1_upper_a_storm_is_23_sets(program: Program) -> None:
    s = build(program, "upper_a", FOUNDATION)
    assert s.sets_needed == 23
    main = item(s, "standing-barbell-overhead-press")
    assert (main.sets, main.rep_min, main.rep_max) == (3, 8, 10)


def test_build_upper_a_is_24_sets_as_written(program: Program) -> None:
    s = build(program, "upper_a", BUILD)
    assert s.sets_needed == 24
    template = program.template("upper_a")
    for pr, it in zip(template.prescriptions, s.items, strict=False):
        assert (it.exercise, it.sets, it.rep_min, it.rep_max, it.rest_seconds) == (
            pr.exercise,
            pr.sets,
            pr.rep_min,
            pr.rep_max,
            pr.rest_seconds,
        )


@pytest.mark.parametrize("code", ["upper_a", "lower_a", "upper_b", "lower_b"])
def test_strength_main_lift_is_5x3_5(program: Program, code: str) -> None:
    s = build(program, code, STRENGTH)
    (main,) = [i for i in s.items if i.is_main_lift]
    assert (main.sets, main.rep_min, main.rep_max) == (5, 3, 5)
    others = [i for i in s.items if not i.is_main_lift]
    assert all(
        i.sets == b.sets
        for i, b in zip(
            others, [i for i in build(program, code, BUILD).items if not i.is_main_lift], strict=True
        )
    )


@pytest.mark.parametrize(
    ("code", "slug"),
    [
        ("upper_a", "lateral-raise"),
        ("upper_b", "barbell-shrug"),
        ("upper_b", "incline-dumbbell-curl"),
        ("upper_b", "hammer-curl"),
        ("lower_b", "lateral-raise-light"),
    ],
)
def test_specialization_extra_sets(program: Program, code: str, slug: str) -> None:
    (base,) = [p.sets for p in program.template(code).prescriptions if p.exercise == slug]
    assert item(build(program, code, BUILD), slug).sets == base
    assert item(build(program, code, SPECIALIZATION), slug).sets == base + 2


def test_specialization_adds_exactly_the_extra_sets(program: Program) -> None:
    extra = phase_for(SPECIALIZATION, program).modifiers.extra_sets
    for t in program.session_templates:
        base = build(program, t.code, BUILD).sets_needed
        added = sum(extra.get(pr.exercise, 0) for pr in t.prescriptions)
        assert build(program, t.code, SPECIALIZATION).sets_needed == base + added


@pytest.mark.parametrize("path", ["storm", "shadow", "titan", "blade"])
def test_engine_resolves_per_path(program: Program, path: str) -> None:
    s = build(program, "engine", BUILD, path)
    (only,) = s.items
    assert only.exercise == program.path(path).conditioning_exercise
    assert only.name == program.exercise(only.exercise).name
    assert (only.sets, only.rep_max) == (1, 1)


@pytest.mark.parametrize("path", ["storm", "shadow", "titan", "blade"])
def test_path_techniques_appended_to_upper_sessions_only(program: Program, path: str) -> None:
    techniques = program.path(path).techniques
    for t in program.session_templates:
        s = build(program, t.code, BUILD, path)
        appended = [i for i in s.items if i.is_technique]
        if t.gets_path_techniques:
            assert [i.exercise for i in s.items[-len(techniques) :]] == [x.exercise for x in techniques]
            assert [(i.sets, i.rep_min, i.rep_max) for i in appended] == [
                (x.sets, x.rep_min, x.rep_max) for x in techniques
            ]
        else:
            assert appended == []
    assert {t.code for t in program.session_templates if t.gets_path_techniques} == {"upper_a", "upper_b"}


@pytest.mark.parametrize("week", [FOUNDATION, BUILD, STRENGTH, SPECIALIZATION, REVEAL])
@pytest.mark.parametrize("path", ["storm", "shadow", "titan", "blade"])
def test_garage_swaps_every_exercise_with_a_swap_and_nothing_else(
    program: Program, week: int, path: str
) -> None:
    for t in program.session_templates:
        gym = build(program, t.code, week, path)
        garage = build(program, t.code, week, path, garage=True)
        assert len(gym.items) == len(garage.items)
        for pr_index, (g, h) in enumerate(zip(gym.items, garage.items, strict=True)):
            # Sets, reps, rest and grouping never change.
            assert (g.sets, g.rep_min, g.rep_max, g.rest_seconds, g.superset_group, g.is_main_lift) == (
                h.sets,
                h.rep_min,
                h.rep_max,
                h.rest_seconds,
                h.superset_group,
                h.is_main_lift,
            )
            prescription = t.prescriptions[pr_index] if pr_index < len(t.prescriptions) else None
            expected = (prescription.garage_swap if prescription else None) or program.exercise(
                g.exercise
            ).swap
            if expected:
                assert (h.exercise, h.is_swap, h.replaces) == (expected, True, g.exercise)
                assert h.name == program.exercise(expected).name
            else:
                assert (h.exercise, h.is_swap, h.replaces) == (g.exercise, False, None)
        assert not any(i.is_swap for i in gym.items)


def test_garage_engine_uses_prescription_swap(program: Program) -> None:
    for path in program.paths:
        (only,) = build(program, "engine", BUILD, path, garage=True).items
        assert (only.exercise, only.is_swap) == ("jump-rope-or-burpee-intervals", True)


def test_garage_keeps_specialization_extra_sets(program: Program) -> None:
    s = build(program, "upper_a", SPECIALIZATION, garage=True)
    swapped = [i for i in s.items if i.replaces == "lateral-raise"]
    assert [(i.exercise, i.sets) for i in swapped] == [("band-lateral-raise", 6)]


def test_trial_weeks_build_templates_as_written(program: Program) -> None:
    assert build(program, "upper_a", 0).sets_needed == build(program, "upper_a", BUILD).sets_needed
