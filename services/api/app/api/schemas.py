"""Response and request shapes (the public API contract; generated into packages/api-types).

Keep these stable: add fields rather than renaming (docs/04-api.md).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- program ---------------------------------------------------------------------------------------------


class ExerciseOut(Model):
    slug: str
    name: str
    equipment: list[str]
    increment_lb: float
    is_timed: bool
    needs_garage_space: bool
    swap: str | None


class PrescriptionOut(Model):
    exercise: str  # exercise slug, or "PATH_CONDITIONING" (filled from the path)
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int | None
    is_main_lift: bool
    superset_group: str | None
    note: str | None
    garage_swap: str | None


class SessionTemplateOut(Model):
    code: str
    name: str
    short: str
    kind: str
    day_of_week: int
    gets_path_techniques: bool
    required_for_full_week: bool
    prescriptions: list[PrescriptionOut]


class SetSchemeOut(Model):
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int | None = None


class OptionalDayOut(Model):
    day_of_week: int
    name: str
    prescriptions: list[PrescriptionOut]


class PhaseModifiersOut(Model):
    main_lift_scheme: SetSchemeOut | None
    main_lift_rir: list[int] | None
    extra_sets: dict[str, int]
    optional_day: OptionalDayOut | None
    extra_conditioning_sessions: int
    diet_break_week: int | None
    progression: str | None
    next: str | None


class PhaseOut(Model):
    ord: int
    name: str
    kind: str
    start_week: int
    end_week: int
    rir_target: int | None
    calorie_mode: str
    deload_every: int | None
    display_name_template: str | None
    modifiers: PhaseModifiersOut


class TechniqueStepOut(Model):
    exercise: str
    name: str


class PathTechniqueOut(Model):
    exercise: str
    name: str
    sets: int
    rep_min: int
    rep_max: int
    note: str | None
    rest_seconds: int | None = None
    steps: list[TechniqueStepOut] = []  # progression steps, easiest first


class PathOut(Model):
    slug: str
    name: str
    tagline: str
    build: str
    ratio_target: float
    colors: dict[str, str]
    emphasis: dict[str, int]
    techniques: list[PathTechniqueOut]
    conditioning: str
    conditioning_exercise: str


class TestDefOut(Model):
    type: str
    label: str
    unit: str
    how: str


class BadgeRuleOut(Model):
    metric: str
    gte: float


class BadgeOut(Model):
    slug: str
    name: str
    description: str
    xp_reward: int
    rule: BadgeRuleOut


class RankOut(Model):
    from_level: int
    name: str


class ProgramOut(Model):
    slug: str
    version: int
    name: str
    cycle_weeks: int
    exercises: list[ExerciseOut]
    phases: list[PhaseOut]
    session_templates: list[SessionTemplateOut]
    paths: list[PathOut]
    tests: list[TestDefOut]
    badges: list[BadgeOut]
    ranks: list[RankOut]
