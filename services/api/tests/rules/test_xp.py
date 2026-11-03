"""XP, levels and ranks: docs/03-program-rules.md section 3 and the golden values."""

import datetime as dt
import itertools

import pytest

from app.rules.calendar import phase_for
from app.rules.completion import LoggedSet, score_session
from app.rules.program import Program
from app.rules.sessions import BuiltSession, build_session
from app.rules.xp import (
    Award,
    badge_award,
    dedupe,
    full_week_award,
    level,
    level_progress,
    rank_for,
    scan_award,
    session_awards,
    total_xp,
    trial_award,
    xp_for_level,
)

T0 = dt.datetime(2026, 1, 5, 6, 0, tzinfo=dt.UTC)
_ids = itertools.count()
ENROLLMENT = "enr-1"


def logged(exercise: str, reps: int, *, minute: int = 0, supersedes: str | None = None) -> LoggedSet:
    return LoggedSet(
        id=f"s{next(_ids)}",
        exercise=exercise,
        reps=reps,
        logged_at=T0 + dt.timedelta(minutes=minute),
        supersedes=supersedes,
    )


def build(program: Program, code: str, week: int = 1, path: str = "storm") -> BuiltSession:
    return build_session(program, program.template(code), phase_for(week, program), program.path(path))


def top_sets(s: BuiltSession, short: int = 0) -> list[LoggedSet]:
    out = [logged(i.exercise, i.rep_max) for i in s.items for _ in range(i.sets)]
    return out[: len(out) - short]


def awards_for(program: Program, code: str, sets: list[LoggedSet], session_id: str = "sess-1") -> list[Award]:
    s = build(program, code)
    return session_awards(session_id, program.template(code).kind, score_session(s, sets))


def by_type(awards: list[Award], type_: str) -> int:
    return sum(a.amount for a in awards if a.type == type_)


# --- level curve -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("xp", "lv"), [(0, 1), (399, 1), (400, 2), (4_420, 7), (55_499, 30), (55_500, 31)])
def test_golden_levels(xp: int, lv: int) -> None:
    assert level(xp) == lv


def test_golden_xp_for_level_10() -> None:
    assert xp_for_level(10) == 7_200
    assert xp_for_level(1) == 0


def test_level_exact_at_every_boundary() -> None:
    for lv in range(1, 500):
        b = xp_for_level(lv)
        assert level(b) == lv
        if b > 0:
            assert level(b - 1) == lv - 1


def test_level_huge_xp_is_integer_safe() -> None:
    lv = 1_000_000
    assert level(xp_for_level(lv)) == lv
    assert level(xp_for_level(lv) - 1) == lv - 1


@pytest.mark.parametrize("bad", [-1])
def test_level_rejects_negative(bad: int) -> None:
    with pytest.raises(ValueError):
        level(bad)


def test_level_progress() -> None:
    p = level_progress(740)
    assert (p.level, p.xp_into_level, p.xp_to_next) == (2, 340, 160)


@pytest.mark.parametrize(
    ("lv", "rank"),
    [
        (1, "Rookie"),
        (4, "Rookie"),
        (5, "Fighter"),
        (9, "Fighter"),
        (10, "Warrior"),
        (30, "Mythic"),
        (99, "Mythic"),
    ],
)
def test_golden_ranks(program: Program, lv: int, rank: str) -> None:
    assert rank_for(lv, program).name == rank


# --- awards ----------------------------------------------------------------------------------------------


def test_golden_upper_a_all_top_reps(program: Program) -> None:
    awards = awards_for(program, "upper_a", top_sets(build(program, "upper_a")))
    assert by_type(awards, "set_logged") == 115
    assert by_type(awards, "session_cleared") + by_type(awards, "all_on_target") == 125
    assert total_xp(awards) == 240


def test_golden_upper_a_plus_trial_0(program: Program) -> None:
    awards = awards_for(program, "upper_a", top_sets(build(program, "upper_a")))
    awards.append(trial_award(ENROLLMENT, 0))
    xp = total_xp(awards)
    p = level_progress(xp)
    assert (xp, p.level, rank_for(p.level, program).name, p.xp_to_next) == (740, 2, "Rookie", 160)


def test_golden_upper_a_one_set_short(program: Program) -> None:
    awards = awards_for(program, "upper_a", top_sets(build(program, "upper_a"), short=1))
    assert by_type(awards, "set_logged") == 110
    assert by_type(awards, "session_cleared") + by_type(awards, "all_on_target") == 0


def test_cleared_but_not_on_target_gets_no_bonus(program: Program) -> None:
    s = build(program, "upper_a")
    sets = top_sets(s)
    sets[0] = logged(sets[0].exercise, 1)
    awards = awards_for(program, "upper_a", sets)
    assert (by_type(awards, "session_cleared"), by_type(awards, "all_on_target")) == (100, 0)


@pytest.mark.parametrize("code", ["engine", "easy_cardio"])
def test_golden_conditioning_cleared(program: Program, code: str) -> None:
    awards = awards_for(program, code, top_sets(build(program, code)))
    assert (by_type(awards, "set_logged"), by_type(awards, "session_cleared")) == (5, 50)
    assert by_type(awards, "all_on_target") == 0  # never the +25 bonus


def test_extra_sets_earn_nothing(program: Program) -> None:
    s = build(program, "upper_a")
    sets = top_sets(s) + [logged(s.items[0].exercise, 10) for _ in range(4)]
    assert by_type(awards_for(program, "upper_a", sets), "set_logged") == 115


def test_edited_set_is_not_paid_twice(program: Program) -> None:
    s = build(program, "engine")
    first = logged(s.items[0].exercise, 1)
    before = awards_for(program, "engine", [first])
    edit = logged(first.exercise, 1, minute=5, supersedes=first.id)
    after = awards_for(program, "engine", [first, edit])
    assert [a.key for a in before] == [a.key for a in after]
    assert ("set_logged", first.id) in {a.key for a in after}


def test_replaying_awards_is_idempotent(program: Program) -> None:
    sets = top_sets(build(program, "upper_a"))
    once = awards_for(program, "upper_a", sets)
    assert total_xp(once + once) == total_xp(once) == 240
    assert len(dedupe(once + once)) == len(once)


def test_golden_full_week(program: Program) -> None:
    a = full_week_award(ENROLLMENT, 3)
    assert (a.type, a.amount, a.source_id) == ("full_week", 150, "week:enr-1:3")
    assert total_xp([a, full_week_award(ENROLLMENT, 3)]) == 150
    assert total_xp([a, full_week_award(ENROLLMENT, 4)]) == 300


def test_source_ids(program: Program) -> None:
    badge = program.badges[0]
    assert trial_award(ENROLLMENT, 2).source_id == "trial:enr-1:2"
    assert badge_award(badge) == Award("badge", badge.xp_reward, f"badge:{badge.slug}")
    assert badge_award(badge).amount == 75
    assert scan_award("scan-9") == Award("scan_logged", 50, "scan-9")
    s = build(program, "upper_a")
    awards = awards_for(program, "upper_a", top_sets(s), session_id="sess-7")
    assert {a.source_id for a in awards if a.type != "set_logged"} == {"sess-7"}
