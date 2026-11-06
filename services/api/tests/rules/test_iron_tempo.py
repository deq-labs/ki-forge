"""Iron Tempo: a path with its own block program (EMOM blocks, car-in twins, deload weeks), #64.

Decisions (Joe, 2026-11-06): a completed EMOM round counts as one set (+5 XP); 1RMs are entered;
L1/L2/L3 is picked per session; every 5th week is a deload.
"""

import copy
import datetime as dt
import itertools
import json

import pytest

from app.config import settings
from app.rules.calendar import block_of, phase_for
from app.rules.completion import LoggedSet, is_full_week, score_session
from app.rules.loads import percent_load
from app.rules.program import Program, ProgramError, parse_program
from app.rules.sessions import BuiltSession, build_session, deload_rounds
from app.rules.xp import session_awards

T0 = dt.datetime(2026, 11, 9, 6, 0, tzinfo=dt.UTC)
_ids = itertools.count()


def logged(exercise: str, set_no: int, *, minute: int = 0, slot: str | None = None, **kw) -> LoggedSet:
    return LoggedSet(
        id=kw.pop("id", None) or f"it{next(_ids)}",
        exercise=exercise,
        reps=kw.pop("reps", 3),
        logged_at=T0 + dt.timedelta(minutes=minute),
        set_no=set_no,
        slot=slot,
        **kw,
    )


@pytest.fixture(scope="module")
def it(program: Program) -> Program:
    return program.for_path("iron-tempo")


def build(program: Program, it: Program, code: str, week: int = 0, garage: bool = False) -> BuiltSession:
    phase = phase_for(week, it)
    assert phase is not None
    return build_session(it, it.template(code), phase, program.path("iron-tempo"), garage_mode=garage)


def emom_round(n: int, minute: int = 0, c2b: str = "chest-to-bar-pull-up") -> list[LoggedSet]:
    return [
        logged("conventional-deadlift", n, minute=minute),
        logged(c2b, n, minute=minute + 1),
        logged("calorie-row", n, minute=minute + 2, reps=15),
    ]


# --- program shape ---------------------------------------------------------------------------------------


def test_path_runs_its_own_program(program: Program, it: Program) -> None:
    assert program.path("iron-tempo").program == "iron-tempo"
    assert it.slug == "iron-tempo" and it.repeats and it.cycle_weeks == 5
    assert program.for_path("storm") is program
    # Shared content: the block program sees the same exercises, paths and ranks.
    assert it.exercises is program.exercises and it.ranks is program.ranks
    assert it.one_rm_lifts == (
        "conventional-deadlift",
        "standing-barbell-overhead-press",
        "barbell-back-squat",
        "front-squat",
    )


def test_week_days_and_twins(it: Program) -> None:
    days = [(t.day_of_week, t.code, t.garage_template) for t in it.session_templates if not t.garage_only]
    assert days == [
        (1, "it_pull", "it_pull_in"),
        (2, "it_push", "it_push_in"),
        (4, "it_legs", "it_legs_in"),
        (5, "it_engine", "it_engine_in"),
        (6, "it_pump", None),  # Saturday: optional, car-out only
    ]
    assert [t.code for t in it.session_templates if t.required_for_full_week and not t.garage_only] == [
        "it_pull",
        "it_push",
        "it_legs",
        "it_engine",
    ]


def test_block_weeks_wrap(it: Program) -> None:
    assert [phase_for(w, it).name for w in range(11)] == ["Build"] * 4 + ["Deload"] + ["Build"] * 4 + [
        "Deload",
        "Build",
    ]
    assert [block_of(w, it) for w in (0, 4, 5, 9, 10)] == [1, 1, 2, 2, 3]
    assert phase_for(-1, it) is None


# --- building ---------------------------------------------------------------------------------------------


def test_monday_car_out(program: Program, it: Program) -> None:
    s = build(program, it, "it_pull")
    assert s.template == "it_pull" and s.warmup and "ramp" in s.warmup
    assert [(i.key, i.name, i.sets, i.role) for i in s.items] == [
        ("p0", "21:00 Alt EMOM", 7, "main"),
        ("p1", "Every 2:30 × 6", 6, "finisher"),
        ("p2", "One-arm dumbbell row", 4, "accessory"),
        ("p3", "Core: plank, dead bugs, Pallof press", 3, "core"),
        ("p4", "X3 bar deadlift", 1, "x3"),
        ("p5", "X3 bar curl", 1, "x3"),
    ]
    emom = s.items[0].block
    assert emom is not None and emom.kind == "emom" and emom.minutes == 21
    deadlift = emom.movements[0]
    assert [(t.amount, t.percent) for t in deadlift.levels] == [(3, 75), (3, 80), (3, 85)]
    assert s.items[1].block.minutes == 15  # every 2:30 × 6


def test_garage_mode_runs_the_car_in_twin(program: Program, it: Program) -> None:
    s = build(program, it, "it_pull", garage=True)
    assert s.template == "it_pull_in"
    assert [i.exercise for i in s.items][:5] == [
        "weighted-pull-up",
        "chin-up",
        "australian-row",
        "dead-hang",
        "mountain-climber",
    ]
    assert not any(i.is_swap for i in s.items)  # the twin is already car-in; no per-exercise swaps
    # Push day: dips stay dips on the car-in day (no swap to deficit push-ups).
    assert "dips" in [i.exercise for i in build(program, it, "it_push", garage=True).items]


def test_saturday_has_no_twin(program: Program, it: Program) -> None:
    assert build(program, it, "it_pump", garage=True).template == "it_pump"


@pytest.mark.parametrize(("rounds", "expected"), [(7, 4), (6, 4), (8, 5), (1, 1), (2, 1)])
def test_deload_rounds(it: Program, rounds: int, expected: int) -> None:
    rule = it.phase_by_ord(2).modifiers.deload
    assert deload_rounds(rounds, rule) == expected


def test_deload_week(program: Program, it: Program) -> None:
    s = build(program, it, "it_pull", week=4)
    assert [i.key for i in s.items] == ["p0", "p2", "p3"]  # finisher and X3 skipped
    emom, core = s.items[0], s.items[2]
    assert emom.sets == emom.block.rounds == 4
    assert {t.percent for t in emom.block.movements[0].levels} == {60}  # flat, no build
    assert core.sets == 3  # core work keeps its rounds
    # The next block's first week is back to normal.
    assert build(program, it, "it_pull", week=5).items[0].sets == 7


# --- scoring and XP --------------------------------------------------------------------------------------


def test_round_counts_when_every_movement_is_logged(program: Program, it: Program) -> None:
    s = build(program, it, "it_pull")
    sets = [*emom_round(1), *emom_round(2, minute=3)[:2]]  # round 2 is missing its row
    row = score_session(s, sets).rows[0]
    assert row.sets_logged == 1 and row.on_target is None
    assert row.counted == (sets[0].id,)  # the round's award id is its first movement's set


def test_full_emom_and_xp(program: Program, it: Program) -> None:
    s = build(program, it, "it_pull")
    sets = [x for n in range(1, 8) for x in emom_round(n, minute=3 * n)]
    score = score_session(s, sets)
    assert (score.rows[0].sets_logged, score.rows[0].on_target) == (7, True)
    xp = sum(a.amount for a in session_awards("sess", "lift", score) if a.type == "set_logged")
    assert xp == 7 * 5  # one set (5 XP) per completed round, not per movement


def test_level_swap_counts(program: Program, it: Program) -> None:
    """L1 on Friday is pull-ups instead of chest-to-bar; both count for the movement."""
    s = build(program, it, "it_engine")
    sets = [
        logged("pull-up", 1),
        logged("kettlebell-swing", 1, minute=1),
        logged("calorie-row", 1, minute=2),
    ]
    assert score_session(s, sets).rows[0].sets_logged == 1


def test_slot_routes_the_same_exercise_to_the_right_block(program: Program, it: Program) -> None:
    s = build(program, it, "it_pull")
    finisher = [logged("conventional-deadlift", 1, slot="p1"), logged("barbell-row", 1, minute=1, slot="p1")]
    rows = score_session(s, finisher).rows
    assert (rows[0].sets_logged, rows[1].sets_logged) == (0, 1)
    # Without a slot, a deadlift set goes to the first row that has it (the EMOM).
    rows = score_session(s, [logged("conventional-deadlift", 1), logged("barbell-row", 1)]).rows
    assert (rows[0].sets_logged, rows[1].sets_logged) == (0, 0)


def test_editing_a_set_keeps_the_round_award(program: Program, it: Program) -> None:
    s = build(program, it, "it_pull")
    first = emom_round(1)
    edit = logged("conventional-deadlift", 1, minute=9, supersedes=first[0].id, reps=4)
    assert score_session(s, [*first, edit]).rows[0].counted == (first[0].id,)


def test_rounds_outside_the_block_are_ignored(program: Program, it: Program) -> None:
    s = build(program, it, "it_pull", week=4)  # deload: 4 rounds
    sets = [x for n in range(1, 8) for x in emom_round(n, minute=3 * n)]
    assert score_session(s, sets).rows[0].sets_logged == 4


def test_x3_is_not_judged_on_target(program: Program, it: Program) -> None:
    s = build(program, it, "it_pull")
    row = score_session(s, [logged("x3-bar-curl", 1, reps=22)]).rows[5]
    assert (row.sets_logged, row.on_target) == (1, True)


def test_full_week_accepts_car_in_days(it: Program) -> None:
    assert is_full_week(it, ["it_pull", "it_push_in", "it_legs", "it_engine_in"])
    assert not is_full_week(it, ["it_pull", "it_push", "it_legs"])
    assert is_full_week(it, ["it_pull", "it_push", "it_legs", "it_engine"])  # Saturday is optional


# --- loads -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("percent", "one_rm", "inc", "expected"),
    [
        (80, 305, 5, 245),  # 244 → 245
        (75, 225, 5, 170),  # 168.75 → 170
        (85, 400, 10, 340),
        (70, 135, 5, 95),  # 94.5 → 95
        (60, 100, 2.5, 60),
        (65, 0, 5, 0),
    ],
)
def test_percent_load(percent: float, one_rm: float, inc: float, expected: float) -> None:
    assert percent_load(percent, one_rm, inc) == expected


# --- validation ------------------------------------------------------------------------------------------


@pytest.fixture
def raw() -> dict:
    return json.loads(settings.seed_path.read_text(encoding="utf-8"))


def _pull(data: dict) -> dict:
    return data["programs"][0]["session_templates"][0]


def test_percent_needs_a_1rm_lift(raw: dict) -> None:
    data = copy.deepcopy(raw)
    _pull(data)["prescriptions"][0]["block"]["movements"][1]["levels"][0]["percent"] = 70  # C2B
    with pytest.raises(ProgramError, match="not a 1RM lift"):
        parse_program(data)


def test_garage_twin_must_be_garage_only(raw: dict) -> None:
    data = copy.deepcopy(raw)
    data["programs"][0]["session_templates"][1]["garage_only"] = False
    with pytest.raises(ProgramError, match="garage_only"):
        parse_program(data)


def test_path_program_must_exist(raw: dict) -> None:
    data = copy.deepcopy(raw)
    data["paths"][-1]["program"] = "nope"
    with pytest.raises(ProgramError, match="unknown program"):
        parse_program(data)


def test_block_movements_must_exist(raw: dict) -> None:
    data = copy.deepcopy(raw)
    _pull(data)["prescriptions"][0]["block"]["movements"][0]["exercise"] = "nope"
    with pytest.raises(ProgramError, match="unknown exercise 'nope'"):
        parse_program(data)
