"""Program content model: exercises, phases, session templates, paths, tests, badges and ranks.

Everything here is data from `db/seed/program.json`; nothing about the program is hardcoded.
`load_program(path)` reads the file it is given; `parse_program(data)` builds the model from an
already-decoded dict. Both validate cross-references so a bad seed fails loudly at load time.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

# Placeholder exercise in a session template, replaced by the active path's `conditioning_exercise`.
PATH_CONDITIONING = "PATH_CONDITIONING"

PhaseKind = Literal["trial", "phase"]
SessionKind = Literal["lift", "conditioning"]


class ProgramError(ValueError):
    """The program data is malformed or inconsistent."""


def _frozen_map[K, V](m: Mapping[K, V] | None) -> Mapping[K, V]:
    return MappingProxyType(dict(m or {}))


@dataclass(frozen=True, slots=True)
class Exercise:
    slug: str
    name: str
    equipment: tuple[str, ...]
    increment_lb: float
    is_timed: bool
    needs_garage_space: bool
    swap: str | None  # slug of the garage-mode replacement


@dataclass(frozen=True, slots=True)
class Prescription:
    exercise: str  # exercise slug, or PATH_CONDITIONING
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int | None = None
    is_main_lift: bool = False
    superset_group: str | None = None
    note: str | None = None
    garage_swap: str | None = None  # overrides the exercise's own swap (used for PATH_CONDITIONING)


@dataclass(frozen=True, slots=True)
class SessionTemplate:
    code: str
    name: str
    short: str
    kind: SessionKind
    day_of_week: int  # ISO, Monday = 1
    gets_path_techniques: bool
    required_for_full_week: bool
    prescriptions: tuple[Prescription, ...]

    @property
    def uses_path_conditioning(self) -> bool:
        return any(p.exercise == PATH_CONDITIONING for p in self.prescriptions)


@dataclass(frozen=True, slots=True)
class SetScheme:
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int | None = None  # the phase's rest for the main lift; None = as written


@dataclass(frozen=True, slots=True)
class OptionalDay:
    day_of_week: int
    name: str
    prescriptions: tuple[Prescription, ...]


@dataclass(frozen=True, slots=True)
class PhaseModifiers:
    main_lift_scheme: SetScheme | None = None
    main_lift_rir: tuple[int, ...] | None = None
    extra_sets: Mapping[str, int] = field(default_factory=lambda: _frozen_map(None))
    optional_day: OptionalDay | None = None
    extra_conditioning_sessions: int = 0
    diet_break_week: int | None = None
    progression: str | None = None  # e.g. "hold_weights"
    next: str | None = None  # free-text note on what follows the phase


@dataclass(frozen=True, slots=True)
class Phase:
    ord: int
    name: str
    kind: PhaseKind
    start_week: int
    end_week: int
    rir_target: int | None
    calorie_mode: str
    deload_every: int | None
    modifiers: PhaseModifiers
    display_name_template: str | None = None

    @property
    def is_trial(self) -> bool:
        return self.kind == "trial"

    def contains(self, week: int) -> bool:
        return self.start_week <= week <= self.end_week


@dataclass(frozen=True, slots=True)
class TechniqueStep:
    """One step of a technique progression, e.g. "Box pistol" on the way to a full pistol squat."""

    exercise: str
    name: str


@dataclass(frozen=True, slots=True)
class PathTechnique:
    exercise: str
    name: str
    sets: int
    rep_min: int
    rep_max: int
    note: str | None = None
    rest_seconds: int | None = None
    # Progression steps, easiest first; the last is usually `exercise` itself. Empty = a single exercise.
    steps: tuple[TechniqueStep, ...] = ()

    @property
    def step_slugs(self) -> tuple[str, ...]:
        return tuple(s.exercise for s in self.steps)


@dataclass(frozen=True, slots=True)
class TrainingPath:
    """A character path (Storm Fighter, …). Named to avoid clashing with `pathlib.Path`."""

    slug: str
    name: str
    tagline: str
    build: str
    ratio_target: float
    colors: Mapping[str, str]
    emphasis: Mapping[str, int]
    techniques: tuple[PathTechnique, ...]
    conditioning: str
    conditioning_exercise: str


@dataclass(frozen=True, slots=True)
class TestDef:
    __test__ = False  # not a pytest test class

    type: str
    label: str
    unit: str
    how: str


@dataclass(frozen=True, slots=True)
class BadgeRule:
    metric: str
    gte: float


@dataclass(frozen=True, slots=True)
class Badge:
    slug: str
    name: str
    description: str
    xp_reward: int
    rule: BadgeRule


@dataclass(frozen=True, slots=True)
class Rank:
    from_level: int
    name: str


@dataclass(frozen=True, slots=True)
class Program:
    slug: str
    version: int
    name: str
    cycle_weeks: int
    exercises: Mapping[str, Exercise]  # by slug, seed order preserved
    phases: tuple[Phase, ...]  # ordered by ord
    session_templates: tuple[SessionTemplate, ...]
    paths: Mapping[str, TrainingPath]  # by slug, seed order preserved
    tests: tuple[TestDef, ...]
    badges: tuple[Badge, ...]
    ranks: tuple[Rank, ...]  # ordered by from_level

    def exercise(self, slug: str) -> Exercise:
        return self.exercises[slug]

    def path(self, slug: str) -> TrainingPath:
        return self.paths[slug]

    def template(self, code: str) -> SessionTemplate:
        for t in self.session_templates:
            if t.code == code:
                return t
        raise KeyError(code)

    def phase_by_ord(self, ord_: int) -> Phase:
        for p in self.phases:
            if p.ord == ord_:
                return p
        raise KeyError(ord_)


# --- parsing ---------------------------------------------------------------------------------------------


def _prescription(d: Mapping[str, Any]) -> Prescription:
    return Prescription(
        exercise=d["exercise"],
        sets=d["sets"],
        rep_min=d["rep_min"],
        rep_max=d["rep_max"],
        rest_seconds=d.get("rest_seconds"),
        is_main_lift=d.get("is_main_lift", False),
        superset_group=d.get("superset_group"),
        note=d.get("note"),
        garage_swap=d.get("garage_swap"),
    )


_MODIFIER_KEYS = frozenset(PhaseModifiers.__dataclass_fields__)


def _modifiers(d: Mapping[str, Any], phase_name: str) -> PhaseModifiers:
    unknown = set(d) - _MODIFIER_KEYS
    if unknown:
        raise ProgramError(f"phase {phase_name!r}: unknown modifiers {sorted(unknown)}")
    scheme = d.get("main_lift_scheme")
    rir = d.get("main_lift_rir")
    day = d.get("optional_day")
    return PhaseModifiers(
        main_lift_scheme=SetScheme(**scheme) if scheme else None,
        main_lift_rir=tuple(rir) if rir is not None else None,
        extra_sets=_frozen_map(d.get("extra_sets")),
        optional_day=OptionalDay(
            day_of_week=day["day_of_week"],
            name=day["name"],
            prescriptions=tuple(_prescription(p) for p in day["prescriptions"]),
        )
        if day
        else None,
        extra_conditioning_sessions=d.get("extra_conditioning_sessions", 0),
        diet_break_week=d.get("diet_break_week"),
        progression=d.get("progression"),
        next=d.get("next"),
    )


def _phase(d: Mapping[str, Any]) -> Phase:
    return Phase(
        ord=d["ord"],
        name=d["name"],
        kind=d["kind"],
        start_week=d["start_week"],
        end_week=d["end_week"],
        rir_target=d["rir_target"],
        calorie_mode=d["calorie_mode"],
        deload_every=d["deload_every"],
        modifiers=_modifiers(d.get("modifiers") or {}, d["name"]),
        display_name_template=d.get("display_name_template"),
    )


def _template(d: Mapping[str, Any]) -> SessionTemplate:
    return SessionTemplate(
        code=d["code"],
        name=d["name"],
        short=d["short"],
        kind=d["kind"],
        day_of_week=d["day_of_week"],
        gets_path_techniques=d["gets_path_techniques"],
        required_for_full_week=d["required_for_full_week"],
        prescriptions=tuple(_prescription(p) for p in d["prescriptions"]),
    )


def _path(d: Mapping[str, Any]) -> TrainingPath:
    return TrainingPath(
        slug=d["slug"],
        name=d["name"],
        tagline=d["tagline"],
        build=d["build"],
        ratio_target=d["ratio_target"],
        colors=_frozen_map(d["colors"]),
        emphasis=_frozen_map(d["emphasis"]),
        techniques=tuple(
            PathTechnique(
                exercise=t["exercise"],
                name=t["name"],
                sets=t["sets"],
                rep_min=t["rep_min"],
                rep_max=t["rep_max"],
                note=t.get("note"),
                rest_seconds=t.get("rest_seconds"),
                steps=tuple(
                    TechniqueStep(exercise=s["exercise"], name=s["name"]) for s in t.get("steps", [])
                ),
            )
            for t in d["techniques"]
        ),
        conditioning=d["conditioning"],
        conditioning_exercise=d["conditioning_exercise"],
    )


def _by_key[T](items: Sequence[T], key: str, what: str) -> Mapping[str, T]:
    out: dict[str, T] = {}
    for item in items:
        k = getattr(item, key)
        if k in out:
            raise ProgramError(f"duplicate {what} {k!r}")
        out[k] = item
    return MappingProxyType(out)


def _validate(p: Program) -> None:
    def need(slug: str, where: str) -> None:
        if slug not in p.exercises:
            raise ProgramError(f"{where}: unknown exercise {slug!r}")

    for e in p.exercises.values():
        if e.swap is not None:
            need(e.swap, f"exercise {e.slug!r} swap")
    for t in p.session_templates:
        if not 1 <= t.day_of_week <= 7:
            raise ProgramError(f"template {t.code!r}: day_of_week {t.day_of_week} not in 1..7")
        for pr in t.prescriptions:
            if pr.exercise != PATH_CONDITIONING:
                need(pr.exercise, f"template {t.code!r}")
            if pr.garage_swap is not None:
                need(pr.garage_swap, f"template {t.code!r} garage_swap")
    for path in p.paths.values():
        need(path.conditioning_exercise, f"path {path.slug!r} conditioning")
        for tech in path.techniques:
            need(tech.exercise, f"path {path.slug!r} technique")
            for step in tech.steps:
                need(step.exercise, f"path {path.slug!r} technique step")
    for ph in p.phases:
        for slug in ph.modifiers.extra_sets:
            need(slug, f"phase {ph.name!r} extra_sets")
        if ph.modifiers.optional_day:
            for pr in ph.modifiers.optional_day.prescriptions:
                need(pr.exercise, f"phase {ph.name!r} optional_day")

    # Phases must tile weeks 0 .. cycle_weeks - 1 with no gaps or overlaps.
    expected = 0
    for ph in p.phases:
        if ph.start_week != expected or ph.end_week < ph.start_week:
            raise ProgramError(
                f"phase {ph.name!r} spans weeks {ph.start_week}-{ph.end_week}; expected start {expected}"
            )
        expected = ph.end_week + 1
    if expected != p.cycle_weeks:
        raise ProgramError(f"phases cover {expected} weeks but cycle_weeks is {p.cycle_weeks}")

    if not p.ranks or p.ranks[0].from_level != 1:
        raise ProgramError("ranks must start at level 1")


def parse_program(data: Mapping[str, Any]) -> Program:
    meta = data["program"]
    program = Program(
        slug=meta["slug"],
        version=meta["version"],
        name=meta["name"],
        cycle_weeks=meta["cycle_weeks"],
        exercises=_by_key(
            [
                Exercise(
                    slug=e["slug"],
                    name=e["name"],
                    equipment=tuple(e["equipment"]),
                    increment_lb=e["increment_lb"],
                    is_timed=e["is_timed"],
                    needs_garage_space=e["needs_garage_space"],
                    swap=e["swap"],
                )
                for e in data["exercises"]
            ],
            "slug",
            "exercise",
        ),
        phases=tuple(sorted((_phase(ph) for ph in data["phases"]), key=lambda ph: ph.ord)),
        session_templates=tuple(_template(t) for t in data["session_templates"]),
        paths=_by_key([_path(pa) for pa in data["paths"]], "slug", "path"),
        tests=tuple(
            TestDef(type=t["type"], label=t["label"], unit=t["unit"], how=t["how"]) for t in data["tests"]
        ),
        badges=tuple(
            Badge(
                slug=b["slug"],
                name=b["name"],
                description=b["description"],
                xp_reward=b["xp_reward"],
                rule=BadgeRule(metric=b["rule"]["metric"], gte=b["rule"]["gte"]),
            )
            for b in data["badges"]
        ),
        ranks=tuple(
            sorted(
                (Rank(from_level=r["from_level"], name=r["name"]) for r in data["ranks"]),
                key=lambda r: r.from_level,
            )
        ),
    )
    _validate(program)
    return program


def load_program(path: Path | str) -> Program:
    """Read and parse a program JSON file (normally `settings.seed_path`)."""
    return parse_program(json.loads(Path(path).read_text(encoding="utf-8")))
