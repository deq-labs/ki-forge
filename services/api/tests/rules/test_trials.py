"""Trials, frame ratio and Power Level: docs/03-program-rules.md section 4."""

import datetime as dt

import pytest

from app.rules.program import Program
from app.rules.trials import (
    FrameReading,
    frame_ratio,
    latest_frame_ratio,
    latest_power_level,
    meets_frame_target,
    power_level,
    trial_awards,
    trial_complete,
)
from app.rules.xp import total_xp

GOLDEN = {
    "pullups_max": 8,
    "pushups_max": 30,
    "row_2k_seconds": 510,
    "press_5rm_lb": 115,
    "squat_5rm_lb": 185,
    "deadlift_5rm_lb": 245,
    "bodyweight_lb": 190,
    "shoulders_in": 45.5,
    "waist_in": 34,
}


def test_golden_frame_ratio() -> None:
    assert frame_ratio(45.5, 34) == 1.34


@pytest.mark.parametrize(
    ("shoulders", "waist", "ratio"),
    [
        (50, 40, 1.25),
        (48, 32, 1.5),
        (40.5, 30, 1.35),  # exactly 1.35
        (46.125, 30, 1.54),  # 1.5375 -> half up
        (100.5, 100, 1.01),  # 1.005 -> half up (banker's or float rounding would give 1.0)
        (30, 40, 0.75),
        (0, 34, None),
        (45.5, 0, None),
        (None, 34, None),
        (45.5, None, None),
        (-1, 34, None),
    ],
)
def test_frame_ratio(shoulders, waist, ratio) -> None:
    assert frame_ratio(shoulders, waist) == ratio


def test_golden_power_level() -> None:
    assert power_level(GOLDEN) == 549


def test_power_level_blank_when_no_tests() -> None:
    assert power_level({}) is None
    assert power_level(dict.fromkeys(GOLDEN)) is None


@pytest.mark.parametrize(
    ("row", "term"), [(None, 0), (0, 0), (540, 0), (600, 0), (539, 1), (510, 30), (420, 120)]
)
def test_row_term(row, term: int) -> None:
    base = {**GOLDEN, "row_2k_seconds": None}
    assert power_level({**GOLDEN, "row_2k_seconds": row}) - power_level(base) == term


def test_frame_term_uses_rounded_ratio() -> None:
    no_frame = power_level({**GOLDEN, "shoulders_in": None})
    assert power_level(GOLDEN) - no_frame == 340  # (1.34 - 1) * 1000
    assert power_level({**GOLDEN, "shoulders_in": 51, "waist_in": 34}) - no_frame == 500  # 1.5


def test_frame_term_below_one_is_negative() -> None:
    no_frame = power_level({**GOLDEN, "shoulders_in": None})
    assert power_level({**GOLDEN, "shoulders_in": 30, "waist_in": 40}) - no_frame == -250


def test_lift_terms_floor_to_fives() -> None:
    only = {"press_5rm_lb": 119, "squat_5rm_lb": 4, "deadlift_5rm_lb": 250}
    assert power_level(only) == 23 + 0 + 50


def test_partial_power_level_counts_entered_tests() -> None:
    assert power_level({"pullups_max": 10}) == 50
    assert power_level({"pullups_max": 0}) == 0  # 0 is entered, not blank


def test_trial_complete_and_awards(program: Program) -> None:
    assert trial_complete(GOLDEN, program)
    (award,) = trial_awards("enr-1", 0, GOLDEN, program)
    assert (award.type, award.amount, award.source_id) == ("trial_completed", 500, "trial:enr-1:0")
    assert total_xp(trial_awards("enr-1", 0, GOLDEN, program) * 2) == 500


@pytest.mark.parametrize("missing", list(GOLDEN))
def test_partial_trial_is_not_complete_and_awards_nothing(program: Program, missing: str) -> None:
    partial = {**GOLDEN, missing: None}
    assert not trial_complete(partial, program)
    assert trial_awards("enr-1", 0, partial, program) == []


def test_trial_tests_come_from_program(program: Program) -> None:
    assert {t.type for t in program.tests} == set(GOLDEN)


def test_latest_power_level() -> None:
    assert latest_power_level({}) is None
    assert latest_power_level({0: GOLDEN, 2: {}}) == 549
    assert latest_power_level({0: {"pullups_max": 1}, 2: GOLDEN}) == 549
    assert latest_power_level({0: GOLDEN, 2: {"pullups_max": 1}}) == 5


def test_latest_frame_ratio_from_trials_or_scans() -> None:
    t = dt.datetime(2026, 1, 5, tzinfo=dt.UTC)
    readings = [
        FrameReading(t, 45.5, 34),  # Trial 0: 1.34
        FrameReading(t + dt.timedelta(days=30), 46, 33),  # scan: 1.39
        FrameReading(t + dt.timedelta(days=40), None, 33),  # incomplete, ignored
    ]
    assert latest_frame_ratio(readings) == 1.39
    assert latest_frame_ratio(readings[:1]) == 1.34
    assert latest_frame_ratio([]) is None


@pytest.mark.parametrize(
    ("path", "target"), [("storm", 1.60), ("shadow", 1.45), ("titan", 1.50), ("blade", 1.50)]
)
def test_path_frame_targets(program: Program, path: str, target: float) -> None:
    p = program.path(path)
    assert p.ratio_target == target
    assert meets_frame_target(target, p)
    assert not meets_frame_target(round(target - 0.01, 2), p)
    assert not meets_frame_target(None, p)
