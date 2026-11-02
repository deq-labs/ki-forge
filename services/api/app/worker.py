"""Background worker: claims jobs from the Postgres `jobs` table with FOR UPDATE SKIP LOCKED.

Job handlers (run_progression, analyze_scan, purge_photo, delete_user) arrive in later milestones.
"""

import logging
import time
from collections.abc import Callable

from sqlalchemy import text

from app.db import engine

log = logging.getLogger("kiforge.worker")

HANDLERS: dict[str, Callable[[dict], None]] = {}

CLAIM = text(
    """
    UPDATE jobs SET status = 'running', locked_at = now(), attempts = attempts + 1
    WHERE id = (
        SELECT id FROM jobs
        WHERE status = 'queued' AND run_at <= now() AND kind = ANY(:kinds)
        ORDER BY run_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, kind, payload
    """
)


def run_once() -> bool:
    """Claim and run one job. Returns False when there was nothing to do."""
    with engine.begin() as conn:
        row = conn.execute(CLAIM, {"kinds": list(HANDLERS)}).first()
    if row is None:
        return False
    job_id, kind, payload = row
    try:
        HANDLERS[kind](payload)
    except Exception as exc:  # noqa: BLE001 - record any failure on the job row
        log.exception("job %s (%s) failed", job_id, kind)
        status, error = "failed", repr(exc)
    else:
        status, error = "done", None
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET status = :s, last_error = :e, locked_at = NULL WHERE id = :id"),
            {"s": status, "e": error, "id": job_id},
        )
    return True


def main(poll_seconds: float = 2.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.info("worker started; handlers: %s", sorted(HANDLERS) or "none")
    while True:
        if not run_once():
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
