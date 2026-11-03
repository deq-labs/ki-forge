"""Me and enrollments (issue #21)."""

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BodyScan, TestResult, User, UserStats, XpEvent
from app.services.program import program_ids
from app.services.stats import compute_stats, refresh_stats
from tests.conftest import DEV_USER

MONDAY = "2026-10-26"


def user_id(db: Session) -> uuid.UUID:
    return db.scalar(select(User.id).where(User.email == DEV_USER))


def enroll(client: TestClient, path: str = "storm", start: str = MONDAY) -> dict:
    r = client.post("/v1/enrollments", json={"path_slug": path, "start_date": start})
    assert r.status_code == 201, r.text
    return r.json()


def test_new_user(client: TestClient) -> None:
    body = client.get("/v1/me").json()
    assert body["user"]["email"] == DEV_USER
    assert body["user"]["units"] == "imperial"
    assert body["enrollment"] is None
    assert body["stats"] == {
        "total_xp": 0,
        "level": 1,
        "rank": "Rookie",
        "xp_into_level": 0,
        "xp_to_next": 400,
        "power_level": None,
        "frame_ratio": None,
        "sessions_cleared": 0,
    }
    assert body["badges"] == []


def test_patch_me(client: TestClient) -> None:
    r = client.patch("/v1/me", json={"units": "metric", "timezone": "Europe/London", "display_name": "Joe"})
    assert r.status_code == 200
    user = r.json()["user"]
    assert (user["units"], user["timezone"], user["display_name"]) == ("metric", "Europe/London", "Joe")


@pytest.mark.parametrize(
    "body", [{"units": "furlongs"}, {"timezone": "Mars/Base"}, {"display_name": ""}, {"keep_photos": None}]
)
def test_patch_me_rejects_bad_values(client: TestClient, body: dict) -> None:
    r = client.patch("/v1/me", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_create_enrollment(client: TestClient) -> None:
    e = enroll(client)
    assert (e["path_slug"], e["start_date"], e["cycle"], e["status"]) == ("storm", MONDAY, 1, "active")
    assert client.get("/v1/me").json()["enrollment"]["id"] == e["id"]


def test_second_active_enrollment_rejected(client: TestClient) -> None:
    enroll(client)
    r = client.post("/v1/enrollments", json={"path_slug": "shadow", "start_date": MONDAY})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ({"path_slug": "storm", "start_date": "2026-10-27"}, "Monday"),
        ({"path_slug": "nope", "start_date": MONDAY}, "unknown path"),
        ({"path_slug": "storm"}, "start_date"),
    ],
)
def test_enrollment_validation(client: TestClient, body: dict, needle: str) -> None:
    r = client.post("/v1/enrollments", json=body)
    assert r.status_code == 422
    assert needle in r.json()["error"]["message"]


def test_patch_enrollment(client: TestClient) -> None:
    e = enroll(client)
    r = client.patch(
        f"/v1/enrollments/{e['id']}",
        json={"path_slug": "blade", "start_date": "2026-11-02", "garage_mode_default": True},
    )
    assert r.status_code == 200
    out = r.json()
    assert (out["path_slug"], out["start_date"], out["garage_mode_default"]) == ("blade", "2026-11-02", True)
    assert client.patch(f"/v1/enrollments/{e['id']}", json={"start_date": "2026-11-03"}).status_code == 422


def test_patch_someone_elses_enrollment_is_404(client: TestClient) -> None:
    e = enroll(client)
    other = client.patch(
        f"/v1/enrollments/{e['id']}", json={"path_slug": "titan"}, headers={"X-Dev-User": "x@y.io"}
    )
    assert other.status_code == 404
    assert client.patch(f"/v1/enrollments/{uuid.uuid4()}", json={}).status_code == 404


# --- stats -----------------------------------------------------------------------------------------------


def add_xp(db: Session, uid: uuid.UUID, *events: tuple[str, int, str]) -> None:
    db.add_all(XpEvent(user_id=uid, type=t, amount=a, source_id=s) for t, a, s in events)
    db.flush()


def test_stats_from_events(client: TestClient, db: Session) -> None:
    client.get("/v1/me")
    uid = user_id(db)
    add_xp(db, uid, ("set_logged", 115, "s"), ("session_cleared", 100, "a"), ("all_on_target", 25, "a"))
    add_xp(db, uid, ("trial_completed", 500, "t0"))
    stats = client.get("/v1/me").json()["stats"]
    assert (stats["total_xp"], stats["level"], stats["rank"], stats["xp_to_next"]) == (740, 2, "Rookie", 160)
    assert stats["sessions_cleared"] == 1


def test_power_level_and_frame_ratio(client: TestClient, db: Session) -> None:
    e = enroll(client)
    uid = user_id(db)
    trial0 = program_ids(db).phases[0]
    t0 = dt.datetime(2026, 10, 26, 8, tzinfo=dt.UTC)
    golden = {
        "pullups_max": 8,
        "pushups_max": 30,
        "row_2k_seconds": 510,
        "press_5rm_lb": 115,
        "squat_5rm_lb": 185,
        "deadlift_5rm_lb": 245,
        "bodyweight_lb": 190,
        "shoulders_in": 45.5,
        "waist_in": 34,
    }
    db.add_all(
        TestResult(
            user_id=uid, enrollment_id=uuid.UUID(e["id"]), phase_id=trial0, test=k, value=v, taken_at=t0
        )
        for k, v in golden.items()
    )
    db.flush()
    stats = client.get("/v1/me").json()["stats"]
    assert (stats["power_level"], stats["frame_ratio"]) == (549, 1.34)

    db.add(BodyScan(user_id=uid, shoulders_in=46, waist_in=33, taken_at=t0 + dt.timedelta(days=30)))
    db.flush()
    assert client.get("/v1/me").json()["stats"]["frame_ratio"] == 1.39  # newer scan wins
    db.add(BodyScan(user_id=uid, shoulders_in=40, waist_in=40, taken_at=t0 - dt.timedelta(days=30)))
    db.flush()
    assert client.get("/v1/me").json()["stats"]["frame_ratio"] == 1.39  # older scan does not


def test_user_stats_rebuild_equals_cache(client: TestClient, db: Session) -> None:
    client.get("/v1/me")
    uid = user_id(db)
    add_xp(db, uid, ("set_logged", 5, "a"), ("session_cleared", 100, "b"), ("full_week", 150, "w"))
    cached = refresh_stats(db, uid)
    row = db.get(UserStats, uid)
    rebuilt = compute_stats(db, uid)
    assert rebuilt == cached
    assert (row.total_xp, row.level, row.power_level) == (rebuilt.total_xp, rebuilt.level, 0)
    add_xp(db, uid, ("badge", 75, "badge:first-blood"))
    refresh_stats(db, uid)
    db.refresh(row)
    assert row.total_xp == 330
