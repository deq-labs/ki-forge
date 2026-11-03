"""Background worker: runs jobs from the Postgres `jobs` table (see app/jobs.py).

Run with `python -m app.worker` (the `worker` service in docker-compose.yml, profile `full`).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

import app.services.deletion  # noqa: F401 - registers the delete_user handler
import app.services.progression  # noqa: F401 - registers the run_progression handler
from app.db import SessionLocal
from app.jobs import HANDLERS, run_once

log = logging.getLogger("kiforge.worker")


@contextmanager
def session_scope() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def main(poll_seconds: float = 2.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.info("worker started; handlers: %s", sorted(HANDLERS))
    while True:
        if not run_once(session_scope):
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
