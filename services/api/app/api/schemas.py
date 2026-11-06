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
    setup: str | None = None
    cues: list[str] = []


class TargetOut(Model):
    amount: int | None  # None = max effort
    unit: str  # reps | cal | steps | seconds
    percent: float | None = None  # % of a 1RM
    percent_of: str | None = None  # 1RM lift the percent refers to; None = the movement's own exercise
    weight_lb: float | None = None
    exercise: str | None = None  # this level does a different exercise


class MovementOut(Model):
    exercise: str
    levels: list[TargetOut]  # L1, L2, L3; one entry when the block has no levels
    note: str | None = None


class BlockOut(Model):
    kind: str  # emom | interval | for_time | circuit
    name: str
    rounds: int
    movements: list[MovementOut]
    interval_seconds: int | None = None
    cap_seconds: int | None = None
    rest_seconds: int | None = None
    minutes: float | None = None


class PrescriptionOut(Model):
    exercise: str  # exercise slug, or "PATH_CONDITIONING" (filled from the path); a block's first movement
    sets: int  # a block's rounds
    rep_min: int
    rep_max: int
    rest_seconds: int | None
    is_main_lift: bool
    superset_group: str | None
    note: str | None
    garage_swap: str | None
    role: str | None = None
    block: BlockOut | None = None


class SessionTemplateOut(Model):
    code: str
    name: str
    short: str
    kind: str
    day_of_week: int
    gets_path_techniques: bool
    required_for_full_week: bool
    prescriptions: list[PrescriptionOut]
    garage_template: str | None = None  # garage mode runs this template instead (e.g. the car-in day)
    garage_only: bool = False
    warmup: str | None = None


class SetSchemeOut(Model):
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int | None = None


class OptionalDayOut(Model):
    day_of_week: int
    name: str
    prescriptions: list[PrescriptionOut]


class DeloadRuleOut(Model):
    percent: float
    round_factor: float
    skip_roles: list[str]
    note: str | None = None


class PhaseModifiersOut(Model):
    main_lift_scheme: SetSchemeOut | None
    main_lift_rir: list[int] | None
    extra_sets: dict[str, int]
    optional_day: OptionalDayOut | None
    extra_conditioning_sessions: int
    diet_break_week: int | None
    progression: str | None
    next: str | None
    deload: DeloadRuleOut | None = None


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
    program: str | None = None  # slug in ProgramOut.programs; None = the main arc


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


class BlockProgramOut(Model):
    """A program a path brings instead of the main arc (e.g. Iron Tempo's 5-week block)."""

    slug: str
    version: int
    name: str
    cycle_weeks: int
    repeats: bool
    one_rm_lifts: list[str]
    phases: list[PhaseOut]
    session_templates: list[SessionTemplateOut]


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
    programs: list[BlockProgramOut] = []
