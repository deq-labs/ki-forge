"""Storing Trial results (shared by PUT /v1/trials and the workbook import)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Enrollment, TestResult
from app.services.program import program_ids


def upsert_trial_results(
    db: Session,
    user_id: uuid.UUID,
    enrollment: Enrollment,
    phase_ord: int,
    results: Mapping[str, float | None],
    taken_at: dt.datetime,
) -> None:
    """Write each given test value (None deletes it); tests not given are left as they are."""
    phase_id = program_ids(db).phases[phase_ord]
    key = (TestResult.user_id, TestResult.enrollment_id, TestResult.phase_id, TestResult.test)
    for test, value in results.items():
        if value is None:
            db.execute(
                delete(TestResult).where(
                    TestResult.user_id == user_id,
                    TestResult.enrollment_id == enrollment.id,
                    TestResult.phase_id == phase_id,
                    TestResult.test == test,
                )
            )
            continue
        db.execute(
            insert(TestResult)
            .values(
                user_id=user_id,
                enrollment_id=enrollment.id,
                phase_id=phase_id,
                test=test,
                value=value,
                taken_at=taken_at,
            )
            .on_conflict_do_update(index_elements=list(key), set_={"value": value, "taken_at": taken_at})
        )
