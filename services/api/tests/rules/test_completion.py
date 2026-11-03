"""Completion: docs/03-program-rules.md section 2."""

import datetime as dt
import itertools

import pytest

from app.rules.calendar import phase_for
from app.rules.completion import LoggedSet, is_full_week, latest_sets, score_session
from app.rules.program import Program
from app.rules.sessions import BuiltSession, build_session

T0 = dt.datetime(2026, 1, 5, 6, 0, tzinfo=dt.UTC)
_ids = itertools.count()


def logged(
    exercise: str, reps: int | None, *, minute: int = 0, supersedes: str | None = None, id: str | None = None
):
    return LoggedSet(
        id=id or f"s{next(_ids)}",
        exercise=exercise,
        reps=reps,
        logged_at=T0 + dt.timedelta(minutes=minute),
        supersedes=supersedes,
    )


def build(
    program: Program, code: str, week: int = 1, path: str = "storm", garage: bool = False
) -> BuiltSession:
    return build_session(
        program, program.template(code), phase_for(week, program), program.path(path), garage_mode=garage
    )


def all_sets_at_top(session: BuiltSession, short: int = 0) -> list[LoggedSet]:
    """Every prescribed set at rep_max, minus `short` sets from the last row."""
    out = [logged(i.exercise, i.rep_max) for i in session.items for _ in range(i.sets)]
    return out[: len(out) - short]


# --- golden values ---------------------------------------------------------------------------------------


def test_golden_upper_a_all_sets_at_top_reps(program: Program) -> None:
    s = build(program, "upper_a")
    score = score_session(s, all_sets_at_top(s))
    assert (score.sets_needed, score.sets_logged, score.cleared, score.all_on_target) == (23, 23, True, True)


def test_golden_upper_a_one_set_short(program: Program) -> None:
    s = build(program, "upper_a")
    score = score_session(s, all_sets_at_top(s, short=1))
    assert (score.sets_needed, score.sets_logged, score.cleared, score.all_on_target) == (
        23,
        22,
        False,
        False,
    )
    assert score.rows[-1].on_target is None  # short row is not evaluated
    assert all(r.on_target is True for r in score.rows[:-1])


def test_extra_sets_beyond_prescribed_do_not_count(program: Program) -> None:
    s = build(program, "upper_a")
    sets = all_sets_at_top(s, short=1)
    main = s.items[0]
    sets += [logged(main.exercise, main.rep_max) for _ in range(3)]  # 3 extra on the main lift
    score = score_session(s, sets)
    assert score.rows[0].sets_logged == main.sets
    assert (score.sets_logged, score.cleared) == (22, False)


# --- on target -------------------------------------------------------------------------------------------


def test_below_rep_max_clears_but_is_not_on_target(program: Program) -> None:
    s = build(program, "upper_a")
    sets = all_sets_at_top(s)
    sets[0] = logged(s.items[0].exercise, s.items[0].rep_max - 1)
    score = score_session(s, sets)
    assert (score.cleared, score.all_on_target, score.rows[0].on_target) == (True, False, False)


def test_extra_set_at_top_can_make_row_on_target(program: Program) -> None:
    # "number of logged sets with reps >= rep_max" counts every logged set, not just the first N.
    s = build(program, "upper_a")
    sets = all_sets_at_top(s)
    sets[0] = logged(s.items[0].exercise, 1)
    sets.append(logged(s.items[0].exercise, s.items[0].rep_max))
    assert score_session(s, sets).rows[0].on_target is True


def test_technique_rows_always_on_target_when_complete(program: Program) -> None:
    s = build(program, "upper_a")
    sets = [logged(i.exercise, 0 if i.is_technique else i.rep_max) for i in s.items for _ in range(i.sets)]
    score = score_session(s, sets)
    techniques = [r for r in score.rows if r.item.is_technique]
    assert techniques and all(r.on_target is True for r in techniques)
    assert score.all_on_target


def test_missing_reps_counts_as_logged_but_not_on_target(program: Program) -> None:
    s = build(program, "engine")
    score = score_session(s, [logged(s.items[0].exercise, None)])
    assert (score.cleared, score.all_on_target) == (True, False)


# --- done-style rows (reps = 1) ----------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["storm", "shadow", "titan", "blade"])
def test_engine_done_style(program: Program, path: str) -> None:
    s = build(program, "engine", path=path)
    score = score_session(s, [logged(s.items[0].exercise, 1)])
    assert (score.sets_needed, score.sets_logged, score.cleared, score.all_on_target) == (1, 1, True, True)
    assert score_session(s, []).cleared is False


def test_farmer_carry_done_style(program: Program) -> None:
    s = build(program, "lower_b")
    sets = all_sets_at_top(s)
    carry = [r for r in score_session(s, sets).rows if r.item.exercise == "farmer-carry"][0]
    assert (carry.item.sets, carry.item.rep_max, carry.sets_logged, carry.on_target) == (3, 1, 3, True)


def test_garage_sets_score_against_swapped_exercise(program: Program) -> None:
    s = build(program, "engine", garage=True)
    assert score_session(s, [logged("jump-rope-or-burpee-intervals", 1)]).cleared
    # A swapped row also accepts the exercise it replaces (done as written in a garage session).
    assert score_session(s, [logged(program.path("storm").conditioning_exercise, 1)]).cleared
    assert not score_session(s, [logged("farmer-carry", 1)]).cleared


def test_mixed_garage_session_counts_both(program: Program) -> None:
    s = build(program, "upper_a", garage=True)
    sets = all_sets_at_top(s)
    first = s.items[0]
    assert first.is_swap and first.replaces == "standing-barbell-overhead-press"
    sets = [
        logged(first.replaces, x.reps) if x.exercise == first.exercise else x for x in sets
    ]  # the press was done with the barbell after all
    score = score_session(s, sets)
    assert (score.sets_logged, score.cleared, score.all_on_target) == (23, True, True)
    gym = build(program, "upper_a")  # gym mode does not accept swap slugs
    swapped = [logged(first.exercise, 10) for _ in range(first.sets)]
    assert score_session(gym, swapped).rows[0].sets_logged == 0


def test_empty_session_is_not_cleared(program: Program) -> None:
    score = score_session(BuiltSession(template="x", items=()), [])
    assert (score.sets_needed, score.cleared, score.all_on_target) == (0, False, False)


# --- superseded edits ------------------------------------------------------------------------------------


def test_latest_sets_keeps_newest_row_in_each_chain() -> None:
    a = logged("dips", 8, minute=0, id="a")
    a2 = logged("dips", 10, minute=5, id="a2", supersedes="a")
    a3 = logged("dips", 12, minute=9, id="a3", supersedes="a2")
    b = logged("dips", 9, minute=1, id="b")
    assert [s.id for s in latest_sets([a, b, a2, a3])] == ["b", "a3"]


def test_latest_sets_fork_picks_newest() -> None:
    # Two devices edit the same set; the newer edit wins.
    a = logged("dips", 8, minute=0, id="a")
    x = logged("dips", 10, minute=7, id="x", supersedes="a")
    y = logged("dips", 11, minute=3, id="y", supersedes="a")
    assert [s.id for s in latest_sets([a, x, y])] == ["x"]


@pytest.mark.parametrize("edit_minute", [0, -5])
def test_edit_wins_even_with_same_or_earlier_timestamp(edit_minute: int) -> None:
    # Device clocks differ: an edit is newer than what it supersedes regardless of logged_at.
    # Ids chosen so an id tie-break would pick the original: it must not matter.
    a = logged("dips", 8, minute=0, id="zz-original")
    edit = logged("dips", 12, minute=edit_minute, supersedes=a.id, id="aa-edit")
    assert [s.id for s in latest_sets([a, edit])] == ["aa-edit"]


def test_latest_sets_with_ancestor_outside_batch() -> None:
    x = logged("dips", 10, minute=7, id="x", supersedes="gone")
    y = logged("dips", 11, minute=8, id="y", supersedes="x")
    assert [s.id for s in latest_sets([x, y])] == ["y"]


def test_latest_sets_rejects_cycles() -> None:
    with pytest.raises(ValueError, match="cycle"):
        latest_sets([logged("dips", 1, id="p", supersedes="q"), logged("dips", 1, id="q", supersedes="p")])


def test_edits_do_not_double_count(program: Program) -> None:
    s = build(program, "upper_a")
    sets = all_sets_at_top(s, short=1)
    first = sets[0]
    sets.append(logged(first.exercise, first.reps, minute=10, supersedes=first.id))  # an edit, not a new set
    assert (score_session(s, sets).sets_logged, score_session(s, sets).cleared) == (22, False)


def test_edit_changes_on_target(program: Program) -> None:
    s = build(program, "upper_a")
    sets = all_sets_at_top(s)
    first = sets[0]
    sets.append(logged(first.exercise, 1, minute=10, supersedes=first.id))
    score = score_session(s, sets)
    assert (score.cleared, score.rows[0].on_target) == (True, False)


# --- full week -------------------------------------------------------------------------------------------

REQUIRED = ["upper_a", "lower_a", "engine", "upper_b", "lower_b"]


def test_required_templates_from_seed(program: Program) -> None:
    assert [t.code for t in program.session_templates if t.required_for_full_week] == REQUIRED


@pytest.mark.parametrize(
    ("cleared", "full"),
    [
        (REQUIRED, True),
        (REQUIRED + ["easy_cardio"], True),
        (REQUIRED + ["upper_a"], True),  # repeat sessions are fine
        (REQUIRED[:-1], False),
        (REQUIRED[:-1] + ["easy_cardio"], False),  # easy cardio does not replace a required session
        (["easy_cardio"], False),
        ([], False),
    ],
)
def test_full_week(program: Program, cleared: list[str], full: bool) -> None:
    assert is_full_week(program, cleared) is full
