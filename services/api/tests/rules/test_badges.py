"""Badges (docs/03-program-rules.md section 6) and week-level synthetic fixtures."""

import json

import pytest

from app.config import settings
from app.rules.badges import BadgeMetrics, earned_badges, frame_ratio_vs_target, rule_met
from app.rules.program import Program, parse_program
from tests.rules.factories import log_week, run_week

FOUNDATION = 1


def slugs(badges) -> list[str]:
    return [b.slug for b in badges]


def week_metrics(result, garage: bool = False, **extra) -> BadgeMetrics:
    cleared = len(result.cleared)
    return BadgeMetrics(
        sessions_cleared=cleared,
        full_weeks=int(result.full_week),
        garage_sessions_cleared=cleared if garage else 0,
        **extra,
    )


def test_nothing_earned_at_start(program: Program) -> None:
    assert earned_badges(program, BadgeMetrics()) == []


def test_clean_week(program: Program) -> None:
    result = run_week(program, FOUNDATION, log_week(program, FOUNDATION))
    assert result.full_week and len(result.cleared) == 6
    # Sets 23/15/1/25/17/1 x 5 XP; lifts 125 each (all on target); conditioning 50 each; full week 150:
    # Upper A 240, Lower A 200, Engine 55, Upper B 250, Lower B 210, Easy Cardio 55, full week 150
    assert [s.sets_needed for s in result.scores.values()] == [23, 15, 1, 25, 17, 1]
    assert result.xp == 1_160
    assert slugs(earned_badges(program, week_metrics(result))) == ["first-blood", "week-warrior"]


def test_one_session_short(program: Program) -> None:
    result = run_week(program, FOUNDATION, log_week(program, FOUNDATION, short_code="upper_b"))
    assert not result.full_week
    assert "upper_b" not in result.cleared
    assert slugs(earned_badges(program, week_metrics(result))) == ["first-blood"]


def test_garage_week(program: Program) -> None:
    result = run_week(program, FOUNDATION, log_week(program, FOUNDATION, garage=True))
    assert result.full_week
    assert slugs(earned_badges(program, week_metrics(result, garage=True))) == [
        "first-blood",
        "week-warrior",
        "garage-grinder",
    ]


def test_badges_award_once(program: Program) -> None:
    m = BadgeMetrics(sessions_cleared=10, full_weeks=2, scans=1, level=12)
    first = slugs(earned_badges(program, m))
    assert first == ["first-blood", "week-warrior", "power-reading", "warrior-rank"]
    assert earned_badges(program, m, held=first) == []


@pytest.mark.parametrize(("level", "earned"), [(9, False), (10, True), (30, True)])
def test_warrior_rank_badge(program: Program, level: int, earned: bool) -> None:
    assert ("warrior-rank" in slugs(earned_badges(program, BadgeMetrics(level=level)))) is earned


@pytest.mark.parametrize(
    ("path", "ratio", "earned"),
    [
        ("storm", 1.59, False),
        ("storm", 1.60, True),
        ("shadow", 1.45, True),
        ("titan", 1.49, False),
        ("blade", None, False),
    ],
)
def test_golden_frame_badge(program: Program, path: str, ratio, earned: bool) -> None:
    m = BadgeMetrics(frame_ratio_vs_target=frame_ratio_vs_target(ratio, program.path(path)))
    assert ("golden-frame" in slugs(earned_badges(program, m))) is earned


def test_rules_are_read_from_data() -> None:
    seed = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    for b in seed["badges"]:
        if b["slug"] == "warrior-rank":
            b["rule"]["gte"] = 20
    custom = parse_program(seed)
    assert "warrior-rank" not in slugs(earned_badges(custom, BadgeMetrics(level=10)))
    assert "warrior-rank" in slugs(earned_badges(custom, BadgeMetrics(level=20)))


def test_unknown_metric_fails_loudly(program: Program) -> None:
    seed = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    seed["badges"][0]["rule"]["metric"] = "push_ups_lifetime"
    with pytest.raises(KeyError, match="unknown metric"):
        earned_badges(parse_program(seed), BadgeMetrics())


def test_every_seed_rule_uses_a_known_metric(program: Program) -> None:
    m = BadgeMetrics().as_mapping()
    for b in program.badges:
        rule_met(b, m)  # raises on unknown metric
