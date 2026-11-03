"""Calendar: GET /v1/week and GET /v1/arc (docs/04-api.md, "Calendar")."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, Db
from app.api.errors import ERROR_RESPONSES, ApiError
from app.models import Enrollment, ProgressionStateRow, SetLog, User, WorkoutSession
from app.rules.calendar import phase_display_name, phase_for, session_date
from app.rules.completion import is_full_week, latest_sets
from app.rules.program import Phase, Program
from app.rules.progression import hit_target
from app.services.program import get_program, program_ids
from app.services.sessions import built_for, current_week, logged_sets, score_stored
from app.services.stats import active_enrollment

router = APIRouter(tags=["calendar"], responses=ERROR_RESPONSES)


class PhaseSummary(BaseModel):
    ord: int
    name: str  # display name, e.g. "Storm Fighter Specialization"
    kind: str
    rir_target: int | None


class StepView(BaseModel):
    exercise: str
    name: str
    prefill_weight_lb: float | None


class PrescriptionView(BaseModel):
    exercise: str  # slug to perform with the session's garage setting
    name: str
    swap: str | None  # the other option: the garage swap in gym mode, the original exercise in garage mode
    is_swap: bool
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int | None
    superset_group: str | None
    is_main_lift: bool
    is_path_technique: bool
    note: str | None
    prefill_weight_lb: float | None
    # Technique progressions: the steps, the one you're on (last logged, else the first), and whether your
    # last session on it hit the top of the range on every set (time to try the next step).
    steps: list[StepView] = []
    current_step: str | None = None
    ready_to_advance: bool = False


class SessionView(BaseModel):
    code: str
    name: str
    short: str
    date: dt.date
    kind: str
    required_for_full_week: bool
    garage_mode: bool
    cleared: bool
    sets_needed: int
    sets_logged: int
    prescriptions: list[PrescriptionView]


class WeekOut(BaseModel):
    week: int
    current_week: int  # today's program week (negative before the start date)
    starts_on: dt.date
    phase: PhaseSummary
    full_week: bool
    sessions: list[SessionView]  # empty in Trial weeks: those are test weeks


class ArcPhase(BaseModel):
    ord: int
    name: str
    kind: str
    start_week: int
    end_week: int
    start_date: dt.date
    end_date: dt.date
    status: Literal["past", "current", "future"]


class WeekProgress(BaseModel):
    week: int
    week_in_phase: int  # 1-based
    weeks_in_phase: int
    sessions_cleared: int  # required sessions cleared this week
    sessions_required: int


class ArcOut(BaseModel):
    start_date: dt.date
    current_week: int
    current_phase_ord: int | None
    phases: list[ArcPhase]
    progress: WeekProgress | None  # None before the start date and after the cycle


def _enrollment(db: Db, user: User) -> Enrollment:
    e = active_enrollment(db, user.id)
    if e is None:
        raise ApiError(404, "no_enrollment", "start a run first (POST /v1/enrollments)")
    return e


def _phase_summary(phase: Phase, program: Program, path_slug: str) -> PhaseSummary:
    return PhaseSummary(
        ord=phase.ord,
        name=phase_display_name(phase, program.path(path_slug)),
        kind=phase.kind,
        rir_target=phase.rir_target,
    )


def _week_sessions(db: Db, user: User, e: Enrollment, week: int) -> list[WorkoutSession]:
    return list(
        db.scalars(
            select(WorkoutSession).where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.enrollment_id == e.id,
                WorkoutSession.week == week,
            )
        )
    )


def _steps(db: Db, user: User, program: Program, path_slug: str, item, prefill: dict[str, float]) -> dict:
    """Step fields for a technique row with a progression; empty for every other row."""
    tech = next(
        (t for t in program.path(path_slug).techniques if t.exercise == item.exercise and t.steps), None
    )
    if not item.is_technique or tech is None:
        return {}
    ids = program_ids(db)
    step_ids = [ids.exercises[s] for s in tech.step_slugs]
    last = db.execute(
        select(SetLog.exercise_id, SetLog.workout_session_id)
        .join(WorkoutSession, WorkoutSession.id == SetLog.workout_session_id)
        .where(WorkoutSession.user_id == user.id, SetLog.exercise_id.in_(step_ids))
        .order_by(SetLog.logged_at.desc())
        .limit(1)
    ).first()
    current = ids.exercise_slug(last.exercise_id) if last else tech.steps[0].exercise
    ready = False
    if last:
        ws = db.get(WorkoutSession, last.workout_session_id)
        phase = phase_for(ws.week, program) if ws else None
        logged = [
            s
            for s in logged_sets(db, [last.workout_session_id])[last.workout_session_id]
            if s.exercise == current
        ]
        ready = (
            bool(phase and logged and hit_target(item, latest_sets(logged), phase))
            and current != tech.steps[-1].exercise
        )
    return {
        "steps": [
            StepView(exercise=s.exercise, name=s.name, prefill_weight_lb=prefill.get(s.exercise))
            for s in tech.steps
        ],
        "current_step": current,
        "ready_to_advance": ready,
    }


@router.get("/week", response_model=WeekOut)
def read_week(db: Db, user: CurrentUser, week: int | None = Query(default=None, ge=0)) -> WeekOut:
    """A week's sessions fully built for the user's path, phase and garage default. Default: current week."""
    program = get_program()
    e = _enrollment(db, user)
    ids = program_ids(db)
    path_slug = ids.path_slug(e.path_id)
    today_week = current_week(e, user)
    if week is None:
        week = min(max(today_week, 0), program.cycle_weeks - 1)
    phase = phase_for(week, program)
    if phase is None:
        raise ApiError(
            422,
            "week_out_of_range",
            f"week must be 0..{program.cycle_weeks - 1}; cycle 2 is not available yet",
        )

    stored = _week_sessions(db, user, e, week)
    scores = score_stored(db, program, path_slug, stored)
    by_code: dict[str, list] = {}
    for ws in stored:
        if ws.id in scores:
            by_code.setdefault(ids.template_code(ws.session_template_id), []).append((ws, scores[ws.id][1]))
    prefill = {
        ids.exercise_slug(ex): float(w)
        for ex, w in db.execute(
            select(ProgressionStateRow.exercise_id, ProgressionStateRow.next_weight_lb).where(
                ProgressionStateRow.user_id == user.id
            )
        )
    }

    sessions: list[SessionView] = []
    if not phase.is_trial:
        for t in program.session_templates:
            logged = by_code.get(t.code, [])
            # The best logged attempt for this template this week; otherwise the user's garage default.
            best = max(logged, key=lambda p: (p[1].cleared, p[1].sets_logged), default=None)
            garage = best[0].garage_mode if best else e.garage_mode_default
            # A logged session keeps the path it was done on; an unstarted one uses the run's current path.
            sess_path = ids.path_slug(best[0].path_id) if best and best[0].path_id else path_slug
            built = built_for(program, sess_path, t.code, week, garage)
            other = built_for(program, sess_path, t.code, week, not garage)
            assert built is not None and other is not None
            sessions.append(
                SessionView(
                    code=t.code,
                    name=t.name,
                    short=t.short,
                    date=session_date(e.started_on, week, t.day_of_week),
                    kind=t.kind,
                    required_for_full_week=t.required_for_full_week,
                    garage_mode=garage,
                    cleared=bool(best and best[1].cleared),
                    sets_needed=built.sets_needed,
                    sets_logged=best[1].sets_logged if best else 0,
                    prescriptions=[
                        PrescriptionView(
                            exercise=item.exercise,
                            name=item.name,
                            swap=alt.exercise if alt.exercise != item.exercise else None,
                            is_swap=item.is_swap,
                            sets=item.sets,
                            rep_min=item.rep_min,
                            rep_max=item.rep_max,
                            rest_seconds=item.rest_seconds,
                            superset_group=item.superset_group,
                            is_main_lift=item.is_main_lift,
                            is_path_technique=item.is_technique,
                            note=item.note,
                            prefill_weight_lb=prefill.get(item.exercise),
                            **_steps(db, user, program, sess_path, item, prefill),
                        )
                        for item, alt in zip(built.items, other.items, strict=True)
                    ],
                )
            )

    return WeekOut(
        week=week,
        current_week=today_week,
        starts_on=session_date(e.started_on, week, 1),
        phase=_phase_summary(phase, program, path_slug),
        full_week=is_full_week(program, [s.code for s in sessions if s.cleared]),
        sessions=sessions,
    )


@router.get("/arc", response_model=ArcOut)
def read_arc(db: Db, user: CurrentUser) -> ArcOut:
    """Phases with dates and status, plus progress through the current week."""
    program = get_program()
    e = _enrollment(db, user)
    path_slug = program_ids(db).path_slug(e.path_id)
    week = current_week(e, user)
    current = phase_for(week, program)

    def status(ph: Phase) -> Literal["past", "current", "future"]:
        if ph.end_week < week:
            return "past"
        return "current" if ph.contains(week) else "future"

    phases = [
        ArcPhase(
            ord=ph.ord,
            name=phase_display_name(ph, program.path(path_slug)),
            kind=ph.kind,
            start_week=ph.start_week,
            end_week=ph.end_week,
            start_date=session_date(e.started_on, ph.start_week, 1),
            end_date=session_date(e.started_on, ph.end_week, 7),
            status=status(ph),
        )
        for ph in program.phases
    ]
    progress = None
    if current is not None:
        stored = _week_sessions(db, user, e, week)
        scores = score_stored(db, program, path_slug, stored)
        ids = program_ids(db)
        cleared = {
            ids.template_code(ws.session_template_id)
            for ws in stored
            if ws.id in scores and scores[ws.id][1].cleared
        }
        required = [t.code for t in program.session_templates if t.required_for_full_week]
        progress = WeekProgress(
            week=week,
            week_in_phase=week - current.start_week + 1,
            weeks_in_phase=current.end_week - current.start_week + 1,
            sessions_cleared=sum(code in cleared for code in required),
            sessions_required=0 if current.is_trial else len(required),
        )
    return ArcOut(
        start_date=e.started_on,
        current_week=week,
        current_phase_ord=current.ord if current else None,
        phases=phases,
        progress=progress,
    )
