"""Postgres job queue (the `jobs` table). No Redis: workers claim with `FOR UPDATE SKIP LOCKED`.

A job is queued → running → done. A failure goes back to queued with exponential backoff, and becomes
`failed` (dead) after MAX_ATTEMPTS. A job left `running` by a crashed worker is reclaimed after
STALE_AFTER.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Job

log = logging.getLogger("kiforge.jobs")

MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 15  # 15 s, 30 s, 60 s, 120 s ...
STALE_AFTER = dt.timedelta(minutes=10)

Handler = Callable[[Session, dict[str, Any]], None]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


def enqueue(db: Session, kind: str, payload: dict[str, Any], run_at: dt.datetime | None = None) -> Job:
    job = Job(kind=kind, payload=payload, **({"run_at": run_at} if run_at else {}))
    db.add(job)
    return job


CLAIM = text(
    """
    UPDATE jobs SET status = 'running', locked_at = now(), attempts = attempts + 1
    WHERE id = (
        SELECT id FROM jobs
        WHERE kind = ANY(:kinds)
          AND ((status = 'queued' AND run_at <= now())
               OR (status = 'running' AND locked_at < now() - make_interval(secs => :stale)))
        ORDER BY run_at, id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, kind, payload, attempts
    """
)


def claim(db: Session, kinds: list[str] | None = None) -> tuple[int, str, dict, int] | None:
    """Claim one ready job (the caller commits to release the row lock)."""
    row = db.execute(
        CLAIM, {"kinds": kinds if kinds is not None else list(HANDLERS), "stale": STALE_AFTER.total_seconds()}
    ).first()
    return tuple(row) if row else None  # type: ignore[return-value]


def run_once(session_scope: Callable[[], AbstractContextManager[Session]]) -> bool:
    """Claim and run one job. Returns False when nothing was ready."""
    with session_scope() as db:
        claimed = claim(db)
        db.commit()
    if claimed is None:
        return False
    job_id, kind, payload, attempts = claimed
    try:
        with session_scope() as db:
            HANDLERS[kind](db, payload)
            db.commit()
    except Exception as exc:  # noqa: BLE001 - any failure is recorded on the job row
        log.exception("job %s (%s) failed on attempt %s", job_id, kind, attempts)
        dead = attempts >= MAX_ATTEMPTS
        with session_scope() as db:
            db.execute(
                text(
                    "UPDATE jobs SET status = :s, last_error = :e, locked_at = NULL, "
                    "run_at = now() + make_interval(secs => :delay) WHERE id = :id"
                ),
                {
                    "s": "failed" if dead else "queued",
                    "e": repr(exc)[:2000],
                    "delay": 0 if dead else BACKOFF_SECONDS * 2 ** (attempts - 1),
                    "id": job_id,
                },
            )
            db.commit()
        return True
    with session_scope() as db:
        db.execute(
            text("UPDATE jobs SET status = 'done', last_error = NULL, locked_at = NULL WHERE id = :id"),
            {"id": job_id},
        )
        db.commit()
    return True
