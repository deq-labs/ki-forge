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
from app.rules.calendar import block_of, phase_display_name, phase_for, session_date
from app.rules.completion import is_full_week, latest_sets
from app.rules.loads import percent_load
from app.rules.program import Block, Movement, Phase, Program, Target
from app.rules.progression import hit_target
from app.services.lifts import Lift, user_lifts
from app.services.program import get_program, program_ids
from app.services.sessions import built_for, current_week, logged_sets, score_stored
from app.services.stats import active_enrollment

router = APIRouter(tags=["calendar"], responses=ERROR_RESPONSES)


class PhaseSummary(BaseModel):
    ord: int
    name: str  # display name, e.g. "Storm Fighter Specialization"
    kind: str
    rir_target: int | None
    block: int | None = None  # 1-based block number in a repeating block program (Iron Tempo)
    deload_note: str | None = None  # set in a deload week


class LevelView(BaseModel):
    amount: int | None  # None = max effort
    unit: str  # reps | cal | steps | seconds
    percent: float | None  # % of a 1RM
    weight_lb: float | None  # from your 1RM for a % target (None until it is entered), else the fixed load
    exercise: str  # exercise done at this level
    name: str


class MovementView(BaseModel):
    exercise: str
    name: str
    note: str | None
    levels: list[LevelView]  # L1, L2, L3; one entry when the block has no levels


class BlockView(BaseModel):
    kind: str  # emom | interval | for_time | circuit
    name: str
    rounds: int
    interval_seconds: int | None
    cap_seconds: int | None
    rest_seconds: int | None
    minutes: float | None
    movements: list[MovementView]


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
    key: str = ""  # row id within the session; sent as a set's `slot`
    role: str | None = None  # main, finisher, accessory, core, x3, ...
    block: BlockView | None = None  # timed multi-movement work; sets = rounds


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
    warmup: str | None = None
    garage_twin: bool = False  # garage mode runs a whole different day (e.g. the car-in calisthenics day)
    # For a day with a twin: the other version's rows and warm-up, so switching works offline.
    twin_prescriptions: list[PrescriptionView] | None = None
    twin_warmup: str | None = None
    # False for a car-out-only day of a block program (Iron Tempo Saturday): hidden in garage mode.
    available_in_garage: bool = True


class WeekOut(BaseModel):
    week: int
    current_week: int  # today's program week (negative before the start date)
    starts_on: dt.date
    phase: PhaseSummary
    full_week: bool
    sessions: list[SessionView]  # empty in Trial weeks: those are test weeks
    lifts_needed: list[str] = []  # 1RM lifts this week's % targets need that you have not entered


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
    block: int | None = None  # current block of a repeating block program; phases are that block's


def _enrollment(db: Db, user: User) -> Enrollment:
    e = active_enrollment(db, user.id)
    if e is None:
        raise ApiError(404, "no_enrollment", "start a run first (POST /v1/enrollments)")
    return e


def _phase_summary(phase: Phase, program: Program, path_slug: str, week: int) -> PhaseSummary:
    deload = phase.modifiers.deload
    return PhaseSummary(
        ord=phase.ord,
        name=phase_display_name(phase, program.path(path_slug)),
        kind=phase.kind,
        rir_target=phase.rir_target,
        block=block_of(week, program),
        deload_note=(deload.note or "Deload week") if deload else None,
    )


def _level(program: Program, m: Movement, t: Target, lifts: dict[str, Lift]) -> LevelView:
    exercise = t.exercise or m.exercise
    weight = t.weight_lb
    if t.percent is not None:
        lift = lifts.get(t.percent_of or m.exercise)
        increment = program.exercise(exercise).increment_lb
        weight = percent_load(t.percent, lift.one_rm_lb, increment) if lift else None
    return LevelView(
        amount=t.amount,
        unit=t.unit,
        percent=t.percent,
        weight_lb=weight,
        exercise=exercise,
        name=program.exercise(exercise).name,
    )


def _block_view(program: Program, block: Block, lifts: dict[str, Lift]) -> BlockView:
    return BlockView(
        kind=block.kind,
        name=block.name,
        rounds=block.rounds,
        interval_seconds=block.interval_seconds,
        cap_seconds=block.cap_seconds,
        rest_seconds=block.rest_seconds,
        minutes=block.minutes,
        movements=[
            MovementView(
                exercise=m.exercise,
                name=program.exercise(m.exercise).name,
                note=m.note,
                levels=[_level(program, m, t, lifts) for t in m.levels],
            )
            for m in block.movements
        ],
    )


def _lifts_used(block: Block) -> list[str]:
    return [t.percent_of or m.exercise for m in block.movements for t in m.levels if t.percent is not None]


def _cleared_days(program: Program, cleared: set[str]) -> set[str]:
    """Day templates cleared this week: a cleared car-in twin clears its day."""
    return {
        t.code
        for t in program.session_templates
        if not t.garage_only and (t.code in cleared or (t.garage_template or "") in cleared)
    }


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
    base = get_program()
    e = _enrollment(db, user)
    ids = program_ids(db)
    path_slug = ids.path_slug(e.path_id)
    program = base.for_path(path_slug)  # a path may run its own block program
    today_week = current_week(e, user)
    if week is None:
        week = max(today_week, 0) if program.repeats else min(max(today_week, 0), program.cycle_weeks - 1)
    phase = phase_for(week, program)
    if phase is None:
        raise ApiError(
            422,
            "week_out_of_range",
            f"week must be 0..{program.cycle_weeks - 1}; cycle 2 is not available yet",
        )

    stored = _week_sessions(db, user, e, week)
    scores = score_stored(db, base, path_slug, stored)
    lifts = user_lifts(db, user.id)
    needed: set[str] = set()
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
            if t.garage_only:
                continue  # reached through its day's garage mode
            logged = by_code.get(t.code, [])
            # The best logged attempt for this template this week; otherwise the user's garage default.
            best = max(logged, key=lambda p: (p[1].cleared, p[1].sets_logged), default=None)
            garage = best[0].garage_mode if best else e.garage_mode_default
            # A logged session keeps the path it was done on; an unstarted one uses the run's current path.
            sess_path = ids.path_slug(best[0].path_id) if best and best[0].path_id else path_slug
            built = built_for(base, sess_path, t.code, week, garage)
            # The per-row alternative; a day with a whole car-in twin has none.
            other = None if t.garage_template else built_for(base, sess_path, t.code, week, not garage)
            assert built is not None
            alts = list(other.items) if other is not None else [None] * len(built.items)

            def views(b, alts: list, sess_path: str) -> list[PrescriptionView]:
                rows = []
                for item, alt in zip(b.items, alts, strict=True):
                    if item.block is not None:
                        needed.update(x for x in _lifts_used(item.block) if x not in lifts)
                    rows.append(
                        PrescriptionView(
                            exercise=item.exercise,
                            name=item.name,
                            swap=alt.exercise if alt is not None and alt.exercise != item.exercise else None,
                            is_swap=item.is_swap,
                            sets=item.sets,
                            rep_min=item.rep_min,
                            rep_max=item.rep_max,
                            rest_seconds=item.rest_seconds,
                            superset_group=item.superset_group,
                            is_main_lift=item.is_main_lift,
                            is_path_technique=item.is_technique,
                            note=item.note,
                            prefill_weight_lb=None if item.block else prefill.get(item.exercise),
                            **_steps(db, user, base, sess_path, item, prefill),
                            key=item.key,
                            role=item.role,
                            block=_block_view(base, item.block, lifts) if item.block else None,
                        )
                    )
                return rows

            twin = built_for(base, sess_path, t.code, week, not garage) if t.garage_template else None
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
                    warmup=built.warmup,
                    garage_twin=t.garage_template is not None,
                    prescriptions=views(built, alts, sess_path),
                    twin_prescriptions=views(twin, [None] * len(twin.items), sess_path) if twin else None,
                    twin_warmup=twin.warmup if twin else None,
                    available_in_garage=not (program.repeats and t.garage_template is None),
                )
            )

    return WeekOut(
        week=week,
        current_week=today_week,
        starts_on=session_date(e.started_on, week, 1),
        phase=_phase_summary(phase, program, path_slug, week),
        full_week=is_full_week(program, [s.code for s in sessions if s.cleared]),
        sessions=sessions,
        lifts_needed=[x for x in program.one_rm_lifts if x in needed],
    )


@router.get("/arc", response_model=ArcOut)
def read_arc(db: Db, user: CurrentUser) -> ArcOut:
    """Phases with dates and status, plus progress through the current week.

    A repeating block program (Iron Tempo) shows the current block's phases.
    """
    base = get_program()
    e = _enrollment(db, user)
    path_slug = program_ids(db).path_slug(e.path_id)
    program = base.for_path(path_slug)
    week = current_week(e, user)
    current = phase_for(week, program)
    block = block_of(week, program)
    offset = (block - 1) * program.cycle_weeks if block else 0
    in_block = week - offset  # week within the block (the week itself for the main arc)

    def status(ph: Phase) -> Literal["past", "current", "future"]:
        if ph.end_week < in_block:
            return "past"
        return "current" if ph.contains(in_block) else "future"

    phases = [
        ArcPhase(
            ord=ph.ord,
            name=phase_display_name(ph, program.path(path_slug)),
            kind=ph.kind,
            start_week=ph.start_week + offset,
            end_week=ph.end_week + offset,
            start_date=session_date(e.started_on, ph.start_week + offset, 1),
            end_date=session_date(e.started_on, ph.end_week + offset, 7),
            status=status(ph),
        )
        for ph in program.phases
    ]
    progress = None
    if current is not None:
        stored = _week_sessions(db, user, e, week)
        scores = score_stored(db, base, path_slug, stored)
        ids = program_ids(db)
        cleared = _cleared_days(
            program,
            {
                ids.template_code(ws.session_template_id)
                for ws in stored
                if ws.id in scores and scores[ws.id][1].cleared
            },
        )
        required = [
            t.code for t in program.session_templates if t.required_for_full_week and not t.garage_only
        ]
        progress = WeekProgress(
            week=week,
            week_in_phase=in_block - current.start_week + 1,
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
        block=block,
    )
