"""Progression (docs/03-program-rules.md section 5) over the synthetic fixtures."""

import datetime as dt

import pytest

from app.rules.calendar import phase_for
from app.rules.completion import LoggedSet
from app.rules.program import Program
from app.rules.progression import ProgressionState, progress, round_down, target_rir
from tests.rules.factories import log_session, log_week, run_week

FOUNDATION, BUILD, STRENGTH, SPECIALIZATION, REVEAL = 1, 10, 27, 40, 69


def inc(program: Program, slug: str) -> float:
    return program.exercise(slug).increment_lb


@pytest.mark.parametrize(
    ("weight", "increment", "expected"),
    [(202.5, 5, 200), (202.5, 10, 200), (200, 5, 200), (103.5, 2.5, 102.5), (0, 5, 0), (7, 0, 7)],
)
def test_round_down(weight: float, increment: float, expected: float) -> None:
    assert round_down(weight, increment) == expected


def test_target_rir(program: Program) -> None:
    strength = phase_for(STRENGTH, program)
    assert target_rir(strength, is_main_lift=True) == 2  # main_lift_rir [1, 2]
    assert target_rir(strength, is_main_lift=False) == strength.rir_target
    assert target_rir(phase_for(FOUNDATION, program), is_main_lift=True) == 3


# --- synthetic fixtures ----------------------------------------------------------------------------------


def test_clean_week_progresses_every_exercise(program: Program) -> None:
    logs = log_week(program, FOUNDATION)
    result = run_week(program, FOUNDATION, logs)
    for log in logs:
        for item in log.built.items:
            assert result.states[item.exercise].next_weight_lb == 100 + inc(program, item.exercise)
            assert result.states[item.exercise].stall_count == 0


def test_one_session_short_holds_only_the_short_exercise(program: Program) -> None:
    logs = log_week(program, FOUNDATION, short_code="lower_b")
    result = run_week(program, FOUNDATION, logs)
    short_exercise = logs[4].built.items[-1].exercise  # last row of Lower B lost a set
    assert result.states[short_exercise].next_weight_lb == 100
    others = [i.exercise for i in logs[4].built.items[:-1]]
    assert all(result.states[e].next_weight_lb == 100 + inc(program, e) for e in others)


def test_garage_week_tracks_swaps_separately(program: Program) -> None:
    gym = {"barbell-back-squat": ProgressionState(225)}
    logs = log_week(program, FOUNDATION, garage=True)
    result = run_week(program, FOUNDATION, logs, gym)
    assert result.states["barbell-back-squat"] == ProgressionState(225)  # untouched
    assert result.states["x3-bar-squat"].next_weight_lb == 100 + inc(program, "x3-bar-squat")
    swapped = {i.replaces for log in logs for i in log.built.items if i.is_swap}
    assert not swapped & {k for k in result.states if k != "barbell-back-squat"}


def test_strength_main_lift_5x3_5_progresses_within_rir(program: Program) -> None:
    log = log_session(program, "lower_a", STRENGTH, weight=lambda _: 275, rir=2)
    main = log.built.items[0]
    assert (main.exercise, main.sets, main.rep_min, main.rep_max) == ("barbell-back-squat", 5, 3, 5)
    state = run_week(program, STRENGTH, [log]).states["barbell-back-squat"]
    assert state.next_weight_lb == 275 + inc(program, "barbell-back-squat")


def test_strength_main_lift_rir_above_range_does_not_progress(program: Program) -> None:
    log = log_session(program, "lower_a", STRENGTH, weight=lambda _: 275, rir=3)
    state = run_week(program, STRENGTH, [log]).states["barbell-back-squat"]
    assert state == ProgressionState(275, stall_count=1)


def test_specialization_extra_sets_must_all_hit(program: Program) -> None:
    full = log_session(program, "upper_a", SPECIALIZATION)
    assert [i.sets for i in full.built.items if i.exercise == "lateral-raise"] == [6]
    assert run_week(program, SPECIALIZATION, [full]).states["lateral-raise"].next_weight_lb == 100 + inc(
        program, "lateral-raise"
    )
    # Only the template's original 4 sets: Specialization needs all 6.
    four = log_session(program, "upper_a", SPECIALIZATION)
    four.sets[:] = [s for s in four.sets if not (s.exercise == "lateral-raise" and s.set_no > 4)]
    assert run_week(program, SPECIALIZATION, [four]).states["lateral-raise"].next_weight_lb == 100


def test_stalled_main_lift_drops_10_percent_after_3_sessions(program: Program) -> None:
    def missed(slug: str, top: int) -> int:
        return top - 1 if slug == "barbell-back-squat" else top

    state = {"barbell-back-squat": ProgressionState(225)}
    expected = [ProgressionState(225, 1), ProgressionState(225, 2), ProgressionState(200, 0)]  # 202.5 -> 200
    for week, want in zip([BUILD, BUILD + 1, BUILD + 2], expected, strict=True):
        log = log_session(program, "lower_a", week, reps=missed, weight=lambda _: 225)
        state = run_week(program, week, [log], state).states
        assert state["barbell-back-squat"] == want
    # Accessories that miss only hold; they never drop.
    assert state["romanian-deadlift"].next_weight_lb == 225 + inc(program, "romanian-deadlift")


def test_progress_resets_stall_count(program: Program) -> None:
    log = log_session(program, "lower_a", BUILD, weight=lambda _: 225)
    state = run_week(program, BUILD, [log], {"barbell-back-squat": ProgressionState(225, 2)}).states
    assert state["barbell-back-squat"] == ProgressionState(235, 0)


def test_reveal_week_holds_weights(program: Program) -> None:
    logs = log_week(program, REVEAL)
    before = {"barbell-back-squat": ProgressionState(100, 2)}
    result = run_week(program, REVEAL, logs, before)
    assert all(s.next_weight_lb == 100 for s in result.states.values())
    assert result.states["barbell-back-squat"].stall_count == 2  # holding is not stalling


def test_missing_rir_counts_as_on_target(program: Program) -> None:
    log = log_session(program, "lower_a", BUILD, rir=None)
    assert run_week(program, BUILD, [log]).states["barbell-back-squat"].next_weight_lb == 110


def test_progress_uses_top_logged_weight_and_requires_sets(program: Program) -> None:
    log = log_session(program, "engine", BUILD)
    item = log.built.items[0]
    t = dt.datetime(2026, 3, 9, tzinfo=dt.UTC)
    heavier = [LoggedSet(id="a", exercise=item.exercise, reps=1, logged_at=t, weight_lb=40)]
    assert progress(None, item, heavier, log.phase, 5).next_weight_lb == 45
    with pytest.raises(ValueError):
        progress(None, item, [], log.phase, 5)
