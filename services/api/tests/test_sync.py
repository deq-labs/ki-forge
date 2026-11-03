"""POST /v1/sync (issue #23): idempotent upserts, superseding edits, awards, full week, badges."""

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Job, SetLog, XpEvent

START = dt.date(2026, 10, 26)
T0 = dt.datetime(2026, 11, 2, 7, tzinfo=dt.UTC)
REQUIRED = ["upper_a", "lower_a", "engine", "upper_b", "lower_b"]


@pytest.fixture
def run(client: TestClient) -> dict:
    r = client.post("/v1/enrollments", json={"path_slug": "storm", "start_date": START.isoformat()})
    assert r.status_code == 201
    return r.json()


def week_view(client: TestClient, week: int = 1) -> dict[str, dict]:
    return {s["code"]: s for s in client.get("/v1/week", params={"week": week}).json()["sessions"]}


def session_batch(client: TestClient, code: str, week: int = 1, short: int = 0, garage: bool = False) -> dict:
    """A session with every prescribed set at top reps (technique rows at rep_max too)."""
    view = week_view(client, week)[code]
    sid = str(uuid.uuid4())
    sets = []
    for row in view["prescriptions"]:
        exercise = (row["swap"] or row["exercise"]) if garage and not row["is_swap"] else row["exercise"]
        for n in range(1, row["sets"] + 1):
            sets.append(
                {
                    "client_id": str(uuid.uuid4()),
                    "session_client_id": sid,
                    "exercise_slug": exercise,
                    "set_no": n,
                    "weight_lb": 50,
                    "reps": row["rep_max"],
                    "is_swap": garage and exercise != row["exercise"],
                    "logged_at": (T0 + dt.timedelta(minutes=len(sets))).isoformat(),
                }
            )
    sets = sets[: len(sets) - short]
    session = {
        "client_id": sid,
        "template_code": code,
        "week": week,
        "garage_mode": garage,
        "started_at": T0.isoformat(),
    }
    return {"sessions": [session], "sets": sets}


def sync(client: TestClient, batch: dict, status: int = 200) -> dict:
    r = client.post("/v1/sync", json=batch)
    assert r.status_code == status, r.text
    return r.json()


def xp_rows(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(XpEvent))


def by_type(out: dict, type_: str) -> int:
    return sum(a["amount"] for a in out["xp_awarded"] if a["type"] == type_)


def test_sync_requires_enrollment(client: TestClient) -> None:
    out = sync(client, {"sessions": [], "sets": []}, 404)
    assert out["error"]["code"] == "no_enrollment"


def test_golden_upper_a(client: TestClient, run: dict) -> None:
    out = sync(client, session_batch(client, "upper_a"))
    assert by_type(out, "set_logged") == 115
    assert by_type(out, "session_cleared") + by_type(out, "all_on_target") == 125
    assert [b["slug"] for b in out["new_badges"]] == ["first-blood"]
    assert by_type(out, "badge") == 75
    (session,) = out["sessions"]
    assert (session["cleared"], session["all_on_target"], session["xp"]) == (True, True, 240)
    assert out["stats"]["total_xp"] == 240 + 75
    assert out["stats"]["sessions_cleared"] == 1
    assert out["level_up"] is None
    assert len(out["accepted"]["sets"]) == 23


def test_replay_is_idempotent(client: TestClient, db: Session, run: dict) -> None:
    batch = session_batch(client, "upper_a")
    first = sync(client, batch)
    events = xp_rows(db)
    sets = db.scalar(select(func.count()).select_from(SetLog))
    again = sync(client, batch)
    assert again["xp_awarded"] == [] and again["new_badges"] == [] and again["level_up"] is None
    assert again["stats"] == first["stats"]
    assert again["sessions"] == first["sessions"]
    assert (xp_rows(db), db.scalar(select(func.count()).select_from(SetLog))) == (events, sets)


def test_one_set_short(client: TestClient, run: dict) -> None:
    out = sync(client, session_batch(client, "upper_a", short=1))
    assert by_type(out, "set_logged") == 110
    assert by_type(out, "session_cleared") == 0
    assert out["sessions"][0]["cleared"] is False
    assert out["new_badges"] == []


def test_partial_then_finish(client: TestClient, run: dict) -> None:
    batch = session_batch(client, "upper_a")
    last = batch["sets"].pop()
    sync(client, batch)
    out = sync(client, {"sessions": [], "sets": [last]})
    assert by_type(out, "set_logged") == 5
    assert by_type(out, "session_cleared") + by_type(out, "all_on_target") == 125
    assert out["sessions"][0]["cleared"] is True


def test_golden_engine(client: TestClient, run: dict) -> None:
    out = sync(client, session_batch(client, "engine"))
    assert (by_type(out, "set_logged"), by_type(out, "session_cleared"), by_type(out, "all_on_target")) == (
        5,
        50,
        0,
    )


def test_superseding_edit(client: TestClient, db: Session, run: dict) -> None:
    batch = session_batch(client, "upper_a")
    sync(client, batch)
    first = batch["sets"][0]
    edit = {**first, "client_id": str(uuid.uuid4()), "reps": 1, "supersedes_client_id": first["client_id"]}
    events = xp_rows(db)
    out = sync(client, {"sessions": [], "sets": [edit]})
    assert out["xp_awarded"] == []  # never double-pays the edited set
    assert xp_rows(db) == events
    assert (out["sessions"][0]["cleared"], out["sessions"][0]["all_on_target"]) == (True, False)
    row = db.scalar(select(SetLog).where(SetLog.client_id == uuid.UUID(edit["client_id"])))
    assert row.supersedes_id is not None


def test_edit_chain_in_one_batch_out_of_order(client: TestClient, run: dict) -> None:
    batch = session_batch(client, "engine")
    (orig,) = batch["sets"]
    e1 = {**orig, "client_id": str(uuid.uuid4()), "supersedes_client_id": orig["client_id"]}
    e2 = {**orig, "client_id": str(uuid.uuid4()), "supersedes_client_id": e1["client_id"]}
    batch["sets"] = [e2, e1, orig]
    out = sync(client, batch)
    assert by_type(out, "set_logged") == 5
    assert out["sessions"][0]["cleared"] is True


def test_full_week_bonus_once(client: TestClient, db: Session, run: dict) -> None:
    outs = [sync(client, session_batch(client, code)) for code in REQUIRED]
    assert sum(by_type(o, "full_week") for o in outs) == 150
    assert by_type(outs[-1], "full_week") == 150
    assert [b["slug"] for o in outs for b in o["new_badges"]] == ["first-blood", "week-warrior"]
    # Easy cardio afterwards, and a replay of the last session, award no second bonus.
    assert by_type(sync(client, session_batch(client, "easy_cardio")), "full_week") == 0
    assert db.scalar(select(func.count()).where(XpEvent.type == "full_week")) == 1
    assert week_view(client)["upper_a"]["cleared"] is True
    assert client.get("/v1/week", params={"week": 1}).json()["full_week"] is True


def test_level_up(client: TestClient, run: dict) -> None:
    sync(client, session_batch(client, "upper_a"))  # 315 XP with the badge
    out = sync(client, session_batch(client, "lower_a"))  # +200 -> 515
    assert out["level_up"] == {"from": 1, "to": 2, "rank": "Rookie"}
    assert out["stats"]["level"] == 2


def test_garage_session(client: TestClient, run: dict) -> None:
    out = sync(client, session_batch(client, "upper_a", garage=True))
    assert out["sessions"][0]["cleared"] is True
    assert "garage-grinder" in [b["slug"] for b in out["new_badges"]]


def test_progression_job_enqueued(client: TestClient, db: Session, run: dict) -> None:
    sync(client, session_batch(client, "upper_a"))
    (job,) = db.scalars(select(Job).where(Job.kind == "run_progression"))
    assert job.status == "queued"
    assert len(job.payload["session_ids"]) == 1


def test_set_for_unknown_session_rejected(client: TestClient, run: dict) -> None:
    batch = session_batch(client, "engine")
    batch["sessions"] = []
    out = sync(client, batch, 422)
    assert out["error"]["code"] == "unknown_session"


def test_set_for_another_users_session_rejected(client: TestClient, run: dict) -> None:
    batch = session_batch(client, "engine")
    sync(client, batch)
    other = {"X-Dev-User": "other@example.com"}
    client.post(
        "/v1/enrollments", json={"path_slug": "storm", "start_date": START.isoformat()}, headers=other
    )
    stray = {**batch["sets"][0], "client_id": str(uuid.uuid4())}
    r = client.post("/v1/sync", json={"sessions": [], "sets": [stray]}, headers=other)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "unknown_session")
    r = client.post("/v1/sync", json={"sessions": batch["sessions"], "sets": []}, headers=other)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "client_id_conflict")


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"template_code": "leg_day"}, "unknown_template"),
        ({"week": 0}, "invalid_week"),
        ({"week": 84}, "invalid_week"),
    ],
)
def test_invalid_sessions(client: TestClient, run: dict, patch: dict, code: str) -> None:
    batch = session_batch(client, "engine")
    batch["sessions"][0].update(patch)
    assert sync(client, batch, 422)["error"]["code"] == code


def test_invalid_sets(client: TestClient, run: dict) -> None:
    batch = session_batch(client, "engine")
    batch["sets"][0]["exercise_slug"] = "moon-press"
    assert sync(client, batch, 422)["error"]["code"] == "unknown_exercise"
    batch = session_batch(client, "engine")
    batch["sets"][0]["supersedes_client_id"] = str(uuid.uuid4())
    assert sync(client, batch, 422)["error"]["code"] == "invalid_supersedes"
    batch = session_batch(client, "engine")
    batch["sets"].append(dict(batch["sets"][0]))
    assert sync(client, batch, 422)["error"]["code"] == "duplicate_client_id"
    batch = session_batch(client, "engine")
    batch["sets"][0]["logged_at"] = "2026-11-02T07:00:00"  # no time zone
    assert sync(client, batch, 422)["error"]["code"] == "validation_error"


def test_rejected_batch_writes_nothing(client: TestClient, db: Session, run: dict) -> None:
    batch = session_batch(client, "upper_a")
    batch["sets"][-1]["exercise_slug"] = "moon-press"
    sync(client, batch, 422)
    assert db.scalar(select(func.count()).select_from(SetLog)) == 0
    assert xp_rows(db) == 0
