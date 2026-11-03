"""The `run_progression` job: recompute `progression_state` from the user's stored sessions.

It replays every session in training order (week, then start time) through `rules.progression`, so the
result does not depend on sync order and re-running it never changes the outcome (idempotent).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.jobs import handler
from app.models import Enrollment, ProgressionStateRow, WorkoutSession
from app.rules.calendar import phase_for
from app.rules.progression import ProgressionState, progress_session
from app.services.program import get_program, program_ids
from app.services.sessions import built_for, logged_sets


def recompute_progression(db: Session, user_id: uuid.UUID) -> dict[str, ProgressionState]:
    program = get_program()
    ids = program_ids(db)
    rows = db.execute(
        select(WorkoutSession, Enrollment.path_id)
        .join(Enrollment, Enrollment.id == WorkoutSession.enrollment_id)
        .where(WorkoutSession.user_id == user_id)
        .order_by(Enrollment.started_on, WorkoutSession.week, WorkoutSession.started_at, WorkoutSession.id)
    ).all()
    sets = logged_sets(db, (ws.id for ws, _ in rows))
    states: dict[str, ProgressionState] = {}
    for ws, path_id in rows:
        phase = phase_for(ws.week, program)
        built = built_for(
            program,
            ids.path_slug(path_id),
            ids.template_code(ws.session_template_id),
            ws.week,
            ws.garage_mode,
        )
        if phase is None or built is None or not sets[ws.id]:
            continue
        states = progress_session(program, phase, built, sets[ws.id], states)

    for slug, st in states.items():
        values = {"next_weight_lb": st.next_weight_lb, "stall_count": st.stall_count}
        db.execute(
            insert(ProgressionStateRow)
            .values(user_id=user_id, exercise_id=ids.exercises[slug], **values)
            .on_conflict_do_update(
                index_elements=[ProgressionStateRow.user_id, ProgressionStateRow.exercise_id],
                set_={**values, "updated_at": func.now()},
            )
        )
    return states


@handler("run_progression")
def run_progression(db: Session, payload: dict[str, Any]) -> None:
    recompute_progression(db, uuid.UUID(payload["user_id"]))
