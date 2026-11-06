"""Session builder (docs/03-program-rules.md §1, "Building a session for a given week").

`build_session` turns a session template into the concrete list of exercises for a phase, path and
garage setting. It is pure: all content comes from the `Program` loaded from program.json.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.rules.program import PATH_CONDITIONING, Phase, Program, SessionTemplate, TrainingPath


@dataclass(frozen=True, slots=True)
class SessionItem:
    """One exercise row in a built session."""

    exercise: str  # slug actually performed (after path resolution and garage swaps)
    name: str
    sets: int
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


@dataclass(frozen=True, slots=True)
class BuiltSession:
    template: str  # template code
    items: tuple[SessionItem, ...]

    @property
    def sets_needed(self) -> int:
        return sum(i.sets for i in self.items)


def build_session(
    program: Program,
    template: SessionTemplate,
    phase: Phase,
    path: TrainingPath,
    *,
    garage_mode: bool = False,
) -> BuiltSession:
    mods = phase.modifiers
    items: list[SessionItem] = []
    garage_overrides: dict[int, str] = {}  # item index -> prescription-level garage swap

    # 1-4: template prescriptions, path conditioning, main lift scheme, extra sets.
    for pr in template.prescriptions:
        slug = path.conditioning_exercise if pr.exercise == PATH_CONDITIONING else pr.exercise
        sets, rep_min, rep_max = pr.sets, pr.rep_min, pr.rep_max
        rest = pr.rest_seconds
        if pr.is_main_lift and mods.main_lift_scheme:
            s = mods.main_lift_scheme
            sets, rep_min, rep_max = s.sets, s.rep_min, s.rep_max
            rest = s.rest_seconds or rest
        sets += mods.extra_sets.get(slug, 0)
        if pr.garage_swap:
            garage_overrides[len(items)] = pr.garage_swap
        items.append(
            SessionItem(
                exercise=slug,
                name=program.exercise(slug).name,
                sets=sets,
                rep_min=rep_min,
                rep_max=rep_max,
                rest_seconds=rest,
                is_main_lift=pr.is_main_lift,
                superset_group=pr.superset_group,
                note=pr.note,
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
            )
            for t in path.techniques
        )

    # 6: garage mode swaps; sets, reps and rest stay the same.
    if garage_mode:
        for i, item in enumerate(items):
            swap = garage_overrides.get(i) or program.exercise(item.exercise).swap
            if swap:
                items[i] = replace(
                    item,
                    exercise=swap,
                    name=program.exercise(swap).name,
                    is_swap=True,
                    replaces=item.exercise,
                )

    return BuiltSession(template=template.code, items=tuple(items))
