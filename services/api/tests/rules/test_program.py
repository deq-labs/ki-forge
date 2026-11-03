"""Program loader: round-trips the seed and rejects inconsistent data."""

import copy
import json

import pytest

from app.config import settings
from app.rules.program import PATH_CONDITIONING, Program, ProgramError, parse_program


@pytest.fixture
def seed() -> dict:
    return json.loads(settings.seed_path.read_text(encoding="utf-8"))


def test_seed_counts(program: Program) -> None:
    prescriptions = [p for t in program.session_templates for p in t.prescriptions]
    real = [p for p in prescriptions if p.exercise != PATH_CONDITIONING]
    assert len(program.exercises) == 57  # 52 + 5 technique steps (#58)
    assert (len(real), len(prescriptions) - len(real)) == (25, 1)
    assert len(program.phases) == 11
    assert len(program.paths) == 4
    assert sum(len(p.techniques) for p in program.paths.values()) == 8
    assert len(program.badges) == 6
    # The remaining sections, for completeness.
    assert len(program.session_templates) == 6
    assert len(program.tests) == 9
    assert len(program.ranks) == 7


def test_round_trips_seed_values(program: Program, seed: dict) -> None:
    assert list(program.exercises) == [e["slug"] for e in seed["exercises"]]
    assert [ph.name for ph in program.phases] == [ph["name"] for ph in seed["phases"]]
    assert [t.code for t in program.session_templates] == [t["code"] for t in seed["session_templates"]]
    assert list(program.paths) == [p["slug"] for p in seed["paths"]]
    assert [t.type for t in program.tests] == [t["type"] for t in seed["tests"]]
    assert [b.slug for b in program.badges] == [b["slug"] for b in seed["badges"]]
    assert [(r.from_level, r.name) for r in program.ranks] == [
        (r["from_level"], r["name"]) for r in seed["ranks"]
    ]
    for t_obj, t_raw in zip(program.session_templates, seed["session_templates"], strict=True):
        for p_obj, p_raw in zip(t_obj.prescriptions, t_raw["prescriptions"], strict=True):
            assert (p_obj.exercise, p_obj.sets, p_obj.rep_min, p_obj.rep_max) == (
                p_raw["exercise"],
                p_raw["sets"],
                p_raw["rep_min"],
                p_raw["rep_max"],
            )
            assert p_obj.is_main_lift == p_raw["is_main_lift"]
            assert p_obj.garage_swap == p_raw.get("garage_swap")


def test_phase_modifiers(program: Program, seed: dict) -> None:
    raw = {ph["ord"]: ph for ph in seed["phases"]}
    for ph in program.phases:
        m, r = ph.modifiers, raw[ph.ord]["modifiers"]
        assert dict(m.extra_sets) == r.get("extra_sets", {})
        assert (m.main_lift_scheme is None) == ("main_lift_scheme" not in r)
        if m.main_lift_scheme:
            s = r["main_lift_scheme"]
            assert (m.main_lift_scheme.sets, m.main_lift_scheme.rep_min, m.main_lift_scheme.rep_max) == (
                s["sets"],
                s["rep_min"],
                s["rep_max"],
            )
        assert (m.optional_day is None) == ("optional_day" not in r)
        assert m.progression == r.get("progression")
        assert ph.is_trial == (raw[ph.ord]["kind"] == "trial")


def test_lookups(program: Program) -> None:
    assert program.template("engine").uses_path_conditioning
    assert not program.template("upper_a").uses_path_conditioning
    assert program.phase_by_ord(0).name == program.phases[0].name
    with pytest.raises(KeyError):
        program.template("nope")
    for path in program.paths.values():
        assert program.exercise(path.conditioning_exercise).is_timed


def test_model_is_immutable(program: Program) -> None:
    with pytest.raises(AttributeError):
        program.phases[0].name = "x"  # type: ignore[misc]
    with pytest.raises(TypeError):
        program.exercises["x"] = program.exercises["dips"]  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda s: s["exercises"].append(copy.deepcopy(s["exercises"][0])), "duplicate exercise"),
        (lambda s: s["session_templates"][0]["prescriptions"][0].update(exercise="nope"), "unknown exercise"),
        (lambda s: s["paths"][0].update(conditioning_exercise="nope"), "unknown exercise"),
        (lambda s: s["phases"][1].update(end_week=7), "expected start 8"),
        (lambda s: s["phases"].pop(), "cycle_weeks"),
        (lambda s: s["phases"][1]["modifiers"].update(mystery=1), "unknown modifiers"),
        (lambda s: s["session_templates"][0].update(day_of_week=8), "day_of_week"),
    ],
)
def test_rejects_bad_data(seed: dict, mutate, message: str) -> None:
    mutate(seed)
    with pytest.raises(ProgramError, match=message):
        parse_program(seed)
