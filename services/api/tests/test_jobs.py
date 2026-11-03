"""Job queue and run_progression (issue #25)."""

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select, text, update
from sqlalchemy.orm import Session

from app import jobs
from app.jobs import MAX_ATTEMPTS, claim, enqueue, run_once
from app.models import Job, ProgressionStateRow, User
from app.rules.program import Program
from app.services.program import program_ids
from app.services.progression import recompute_progression
from tests.conftest import DEV_USER
from tests.test_sync import session_batch, sync


@pytest.fixture
def scope(db: Session):
    @contextmanager
    def _scope() -> Iterator[Session]:
        yield db

    return _scope


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    seen: list[dict] = []

    def ok(_db: Session, payload: dict) -> None:
        seen.append(payload)

    def boom(_db: Session, payload: dict) -> None:
        raise RuntimeError("nope")

    monkeypatch.setattr(jobs, "HANDLERS", {"test_ok": ok, "test_boom": boom})
    return seen


def job(db: Session, job_id: int) -> Job:
    db.expire_all()
    return db.get(Job, job_id)


def test_runs_a_job(db: Session, scope, calls: list[dict]) -> None:
    j = enqueue(db, "test_ok", {"n": 1})
    db.flush()
    assert run_once(scope) is True
    assert calls == [{"n": 1}]
    done = job(db, j.id)
    assert (done.status, done.attempts, done.locked_at) == ("done", 1, None)
    assert run_once(scope) is False


def test_only_known_kinds_and_ready_jobs(db: Session, scope, calls: list[dict]) -> None:
    enqueue(db, "someone_elses_kind", {})
    enqueue(db, "test_ok", {}, run_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1))
    db.flush()
    assert run_once(scope) is False


def test_failure_backs_off_then_dies(db: Session, scope, calls: list[dict]) -> None:
    j = enqueue(db, "test_boom", {})
    db.flush()
    run_once(scope)
    retry = job(db, j.id)
    assert (retry.status, retry.attempts) == ("queued", 1)
    assert "nope" in retry.last_error
    assert retry.run_at > db.scalar(select(text("now()")))
    db.execute(update(Job).where(Job.id == j.id).values(attempts=MAX_ATTEMPTS - 1, run_at=text("now()")))
    run_once(scope)
    dead = job(db, j.id)
    assert (dead.status, dead.attempts) == ("failed", MAX_ATTEMPTS)
    assert run_once(scope) is False


def test_stale_running_job_is_reclaimed(db: Session, scope, calls: list[dict]) -> None:
    j = enqueue(db, "test_ok", {"stale": True})
    db.flush()
    db.execute(
        update(Job)
        .where(Job.id == j.id)
        .values(status="running", locked_at=text("now() - interval '1 hour'"))
    )
    assert run_once(scope) is True
    assert calls == [{"stale": True}]


def test_two_workers_never_claim_the_same_job(db_engine: Engine, calls: list[dict]) -> None:
    with Session(db_engine) as setup:
        ids = [enqueue(setup, "test_ok", {"i": i}) for i in range(2)]
        setup.commit()
        ids = [j.id for j in ids]
    try:
        with Session(db_engine) as a, Session(db_engine) as b:
            first = claim(a)
            second = claim(b)  # a still holds its row lock
            third = claim(b)
            assert first and second
            assert first[0] != second[0]
            assert third is None
            a.commit()
            b.commit()
    finally:
        with Session(db_engine) as cleanup:
            cleanup.execute(delete(Job).where(Job.id.in_(ids)))
            cleanup.commit()


# --- run_progression end to end ----------------------------------------------------------------------------


@pytest.fixture
def run(client: TestClient) -> dict:
    r = client.post("/v1/enrollments", json={"path_slug": "storm", "start_date": "2026-10-26"})
    assert r.status_code == 201
    return r.json()


def state(db: Session, slug: str) -> tuple[float, int] | None:
    db.expire_all()
    uid = db.scalar(select(User.id).where(User.email == DEV_USER))
    row = db.get(ProgressionStateRow, (uid, program_ids(db).exercises[slug]))
    return (float(row.next_weight_lb), row.stall_count) if row else None


def drain(scope) -> int:
    n = 0
    while run_once(scope):
        n += 1
    return n


def test_sync_then_worker_progresses(
    client: TestClient, db: Session, scope, run: dict, program: Program
) -> None:
    sync(client, session_batch(client, "upper_a"))  # 50 lb, top reps everywhere
    assert drain(scope) == 1
    ohp = 50 + program.exercise("standing-barbell-overhead-press").increment_lb
    assert state(db, "standing-barbell-overhead-press") == (ohp, 0)
    assert state(db, "lateral-raise") == (50 + program.exercise("lateral-raise").increment_lb, 0)
    prefill = client.get("/v1/week", params={"week": 2}).json()["sessions"][0]["prescriptions"][0]
    assert prefill["prefill_weight_lb"] == ohp


def test_rerunning_progression_is_idempotent(client: TestClient, db: Session, scope, run: dict) -> None:
    sync(client, session_batch(client, "upper_a"))
    drain(scope)
    before = state(db, "standing-barbell-overhead-press")
    uid = db.scalar(select(User.id).where(User.email == DEV_USER))
    recompute_progression(db, uid)
    recompute_progression(db, uid)
    assert state(db, "standing-barbell-overhead-press") == before


def missed_main_lift(client: TestClient, week: int) -> dict:
    batch = session_batch(client, "lower_a", week=week)
    for s in batch["sets"]:
        s["weight_lb"] = 100
        if s["exercise_slug"] == "barbell-back-squat":
            s["reps"] -= 1
    return batch


def test_stalled_main_lift_drops_after_three_sessions(
    client: TestClient, db: Session, scope, run: dict, program: Program
) -> None:
    for week, want in [(1, (100.0, 1)), (2, (100.0, 2)), (3, (90.0, 0))]:
        sync(client, missed_main_lift(client, week))
        drain(scope)
        assert state(db, "barbell-back-squat") == want
    rdl = 100 + program.exercise("romanian-deadlift").increment_lb
    assert state(db, "romanian-deadlift") == (rdl, 0)  # accessories at top reps progress


def test_out_of_order_sync_gives_the_same_state(client: TestClient, db: Session, scope, run: dict) -> None:
    for week in (3, 1, 2):
        sync(client, missed_main_lift(client, week))
    drain(scope)
    assert state(db, "barbell-back-squat") == (90.0, 0)
