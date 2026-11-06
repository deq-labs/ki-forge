"""Session builder (docs/03-program-rules.md §1, "Building a session for a given week").

`build_session` turns a session template into the concrete list of exercises for a phase, path and
garage setting. It is pure: all content comes from the `Program` loaded from program.json.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.rules.program import (
    PATH_CONDITIONING,
    Block,
    DeloadRule,
    Phase,
    Program,
    SessionTemplate,
    TrainingPath,
)


@dataclass(frozen=True, slots=True)
class SessionItem:
    """One exercise row (or one block of timed work) in a built session."""

    exercise: (
        str  # slug actually performed (after path resolution and garage swaps); a block's first movement
    )
    name: str
    sets: int  # a block's rounds
    rep_min: int
    rep_max: int
    rest_seconds: int | None = None
    is_main_lift: bool = False
    superset_group: str | None = None
    note: str | None = None
    is_technique: bool = False  # appended path technique (never evaluated for on-target in v1)
    is_swap: bool = False  # garage-mode replacement
    replaces: str | None = None  # original slug when is_swap
    # Other exercises whose sets also count for this row: a technique's progression steps.
    alternatives: tuple[str, ...] = ()
    # Stable id of the row within its template ("p0", "p1", … for prescriptions, "t0", … for techniques).
    # A logged set may carry it as its `slot` when the same exercise appears in two rows.
    key: str = ""
    role: str | None = None
    block: Block | None = None
    evaluate_target: bool = True  # False: on-target is not judged (techniques, blocks, X3 sets)


@dataclass(frozen=True, slots=True)
class BuiltSession:
    template: str  # template code actually built (the garage twin when garage mode picked it)
    items: tuple[SessionItem, ...]
    warmup: str | None = None

    @property
    def sets_needed(self) -> int:
        return sum(i.sets for i in self.items)


def deload_rounds(rounds: int, rule: DeloadRule) -> int:
    """Block rounds in a deload week: `round(rounds × round_factor)`, at least 1 (half rounds up)."""
    return max(1, int(rounds * rule.round_factor + 0.5))


def _deload_block(block: Block, rule: DeloadRule) -> Block:
    movements = tuple(
        replace(
            m,
            levels=tuple(replace(t, percent=rule.percent) if t.percent is not None else t for t in m.levels),
        )
        for m in block.movements
    )
    # Only EMOM rounds are cut; circuits (core, pump) keep their rounds.
    rounds = deload_rounds(block.rounds, rule) if block.kind == "emom" else block.rounds
    return replace(block, rounds=rounds, movements=movements)


def resolve_template(program: Program, template: SessionTemplate, *, garage_mode: bool) -> SessionTemplate:
    """The template that actually runs: its garage twin in garage mode, if it has one."""
    if garage_mode and template.garage_template:
        return program.template(template.garage_template)
    return template


def build_session(
    program: Program,
    template: SessionTemplate,
    phase: Phase,
    path: TrainingPath,
    *,
    garage_mode: bool = False,
) -> BuiltSession:
    # A whole-day garage twin replaces the template; its exercises are already garage-friendly, so the
    # per-exercise swaps below do not apply to it.
    twin = garage_mode and template.garage_template is not None
    template = resolve_template(program, template, garage_mode=garage_mode)
    mods = phase.modifiers
    deload = mods.deload
    items: list[SessionItem] = []
    garage_overrides: dict[int, str] = {}  # item index -> prescription-level garage swap

    # 1-4: template prescriptions, path conditioning, main lift scheme, extra sets.
    for i, pr in enumerate(template.prescriptions):
        if deload and pr.role in deload.skip_roles:
            continue
        slug = path.conditioning_exercise if pr.exercise == PATH_CONDITIONING else pr.exercise
        sets, rep_min, rep_max = pr.sets, pr.rep_min, pr.rep_max
        rest = pr.rest_seconds
        block = pr.block
        if pr.is_main_lift and mods.main_lift_scheme:
            s = mods.main_lift_scheme
            sets, rep_min, rep_max = s.sets, s.rep_min, s.rep_max
            rest = s.rest_seconds or rest
        if block is not None and deload:
            block = _deload_block(block, deload)
            sets = block.rounds
        sets += mods.extra_sets.get(slug, 0)
        if pr.garage_swap:
            garage_overrides[len(items)] = pr.garage_swap
        items.append(
            SessionItem(
                exercise=slug,
                name=block.name if block else program.exercise(slug).name,
                sets=sets,
                rep_min=rep_min,
                rep_max=rep_max,
                rest_seconds=rest,
                is_main_lift=pr.is_main_lift,
                superset_group=pr.superset_group,
                note=pr.note,
                key=f"p{i}",
                role=pr.role,
                block=block,
                evaluate_target=block is None and pr.role != "x3",
            )
        )

    # 5: path techniques after the template's prescriptions.
    if template.gets_path_techniques:
        items.extend(
            SessionItem(
                exercise=t.exercise,
                name=t.name,
                sets=t.sets,
                rep_min=t.rep_min,
                rep_max=t.rep_max,
                note=t.note,
                rest_seconds=t.rest_seconds,
                is_technique=True,
                alternatives=tuple(s for s in t.step_slugs if s != t.exercise),
                key=f"t{i}",
                evaluate_target=False,
            )
            for i, t in enumerate(path.techniques)
        )

    # 6: garage mode swaps; sets, reps and rest stay the same. Blocks keep their movements.
    if garage_mode and not twin:
        for i, item in enumerate(items):
            if item.block is not None:
                continue
            swap = garage_overrides.get(i) or program.exercise(item.exercise).swap
            if swap:
                items[i] = replace(
                    item,
                    exercise=swap,
                    name=program.exercise(swap).name,
                    is_swap=True,
                    replaces=item.exercise,
                )

    return BuiltSession(template=template.code, items=tuple(items), warmup=template.warmup)
