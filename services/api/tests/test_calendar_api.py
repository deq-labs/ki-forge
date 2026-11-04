"""Calendar endpoints: GET /v1/week and GET /v1/arc (issue #22)."""

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Enrollment, ProgressionStateRow, SetLog, User, WorkoutSession
from app.services.program import program_ids
from app.services.sessions import today_for
from tests.conftest import DEV_USER


def monday_weeks_ago(db: Session, client: TestClient, weeks: int) -> dt.date:
    client.get("/v1/me")  # creates the user
    user = db.scalar(select(User).where(User.email == DEV_USER))
    today = today_for(user)
    return today - dt.timedelta(days=today.weekday()) - dt.timedelta(weeks=weeks)


def enroll(client: TestClient, start: dt.date, path: str = "storm", garage: bool = False) -> dict:
    r = client.post(
        "/v1/enrollments",
        json={"path_slug": path, "start_date": start.isoformat(), "garage_mode_default": garage},
    )
    assert r.status_code == 201, r.text
    return r.json()


def session_view(body: dict, code: str) -> dict:
    (s,) = [s for s in body["sessions"] if s["code"] == code]
    return s


def test_week_requires_enrollment(client: TestClient) -> None:
    r = client.get("/v1/week")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "no_enrollment")
    assert client.get("/v1/arc").status_code == 404


def test_golden_foundation_week1_upper_a_storm(client: TestClient) -> None:
    enroll(client, dt.date(2026, 10, 26))
    body = client.get("/v1/week", params={"week": 1}).json()
    assert body["phase"] == {"ord": 1, "name": "Foundation", "kind": "phase", "rir_target": 3}
    assert [s["code"] for s in body["sessions"]] == [
        "upper_a",
        "lower_a",
        "engine",
        "upper_b",
        "lower_b",
        "easy_cardio",
    ]
    upper_a = session_view(body, "upper_a")
    assert (upper_a["date"], upper_a["sets_needed"], upper_a["sets_logged"], upper_a["cleared"]) == (
        "2026-11-02",
        23,
        0,
        False,
    )
    rows = upper_a["prescriptions"]
    assert (rows[0]["exercise"], rows[0]["sets"], rows[0]["rep_max"], rows[0]["swap"]) == (
        "standing-barbell-overhead-press",
        3,
        10,
        "dumbbell-standing-press",
    )
    assert [r["exercise"] for r in rows if r["is_path_technique"]] == [
        "cable-lateral-raise-drop-set",
        "behind-the-back-shrug",
    ]
    assert session_view(body, "engine")["prescriptions"][0]["exercise"] == "rower-intervals-8-250-m"
    assert body["full_week"] is False


def test_garage_default_returns_swaps(client: TestClient) -> None:
    enroll(client, dt.date(2026, 10, 26), garage=True)
    upper_a = session_view(client.get("/v1/week", params={"week": 1}).json(), "upper_a")
    first = upper_a["prescriptions"][0]
    assert upper_a["garage_mode"] is True
    assert (first["exercise"], first["is_swap"], first["swap"]) == (
        "dumbbell-standing-press",
        True,
        "standing-barbell-overhead-press",
    )
    incline = upper_a["prescriptions"][1]
    assert (incline["exercise"], incline["is_swap"], incline["swap"]) == (
        "incline-dumbbell-press",
        False,
        None,
    )


def test_path_change_rebuilds_future_sessions(client: TestClient) -> None:
    e = enroll(client, dt.date(2026, 10, 26))
    client.patch(f"/v1/enrollments/{e['id']}", json={"path_slug": "shadow"})
    body = client.get("/v1/week", params={"week": 1}).json()
    assert session_view(body, "engine")["prescriptions"][0]["exercise"] == "treadmill-hill-sprints-10-20-s"


def test_trial_week_has_no_sessions(client: TestClient) -> None:
    enroll(client, dt.date(2026, 10, 26))
    body = client.get("/v1/week", params={"week": 0}).json()
    assert (body["phase"]["name"], body["phase"]["kind"], body["sessions"]) == ("Trial 0", "trial", [])
    assert (
        client.get("/v1/week", params={"week": 40}).json()["phase"]["name"] == "Storm Fighter Specialization"
    )


@pytest.mark.parametrize("week", [84, 500])
def test_week_after_cycle_is_422(client: TestClient, week: int) -> None:
    enroll(client, dt.date(2026, 10, 26))
    r = client.get("/v1/week", params={"week": week})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "week_out_of_range")
    assert client.get("/v1/week", params={"week": -1}).status_code == 422


def test_default_week_before_start_is_trial_0(client: TestClient, db: Session) -> None:
    future = monday_weeks_ago(db, client, -3)
    enroll(client, future)
    body = client.get("/v1/week").json()
    assert (body["week"], body["current_week"], body["starts_on"]) == (0, -3, future.isoformat())


def test_default_week_is_current(client: TestClient, db: Session) -> None:
    enroll(client, monday_weeks_ago(db, client, 5))
    body = client.get("/v1/week").json()
    assert (body["week"], body["current_week"], body["phase"]["name"]) == (5, 5, "Foundation")


def test_prefill_from_progression_state(client: TestClient, db: Session) -> None:
    enroll(client, dt.date(2026, 10, 26))
    user = db.scalar(select(User).where(User.email == DEV_USER))
    ids = program_ids(db)
    db.add(
        ProgressionStateRow(
            user_id=user.id, exercise_id=ids.exercises["standing-barbell-overhead-press"], next_weight_lb=100
        )
    )
    db.flush()
    rows = session_view(client.get("/v1/week", params={"week": 1}).json(), "upper_a")["prescriptions"]
    assert rows[0]["prefill_weight_lb"] == 100
    assert rows[1]["prefill_weight_lb"] is None


def log_upper_a(db: Session, enrollment_id: str, week: int = 1, short: int = 0) -> None:
    """Insert a stored Upper A session with every set at top reps (sync arrives in #23)."""
    user = db.scalar(select(User).where(User.email == DEV_USER))
    ids = program_ids(db)
    ws = WorkoutSession(
        client_id=uuid.uuid4(),
        user_id=user.id,
        enrollment_id=uuid.UUID(enrollment_id),
        session_template_id=ids.templates["upper_a"],
        phase_id=ids.phases[1],
        week=week,
        started_at=dt.datetime(2026, 11, 2, 7, tzinfo=dt.UTC),
    )
    db.add(ws)
    db.flush()
    plan = [
        ("standing-barbell-overhead-press", 3, 10),
        ("incline-dumbbell-press", 3, 12),
        ("lateral-raise", 4, 20),
        ("cable-face-pull", 3, 20),
        ("dips", 3, 12),
        ("overhead-cable-triceps-extension", 3, 15),
        ("cable-lateral-raise-drop-set", 2, 12),
        ("behind-the-back-shrug", 2, 15),
    ]
    sets = [(slug, n, top) for slug, count, top in plan for n in range(1, count + 1)]
    for i, (slug, n, top) in enumerate(sets[: len(sets) - short]):
        db.add(
            SetLog(
                client_id=uuid.uuid4(),
                workout_session_id=ws.id,
                exercise_id=ids.exercises[slug],
                set_no=n,
                weight_lb=50,
                reps=top,
                logged_at=ws.started_at + dt.timedelta(minutes=i),
            )
        )
    db.flush()


def test_logged_session_shows_cleared(client: TestClient, db: Session) -> None:
    e = enroll(client, dt.date(2026, 10, 26))
    log_upper_a(db, e["id"])
    upper_a = session_view(client.get("/v1/week", params={"week": 1}).json(), "upper_a")
    assert (upper_a["cleared"], upper_a["sets_logged"]) == (True, 23)


def test_partial_session_not_cleared(client: TestClient, db: Session) -> None:
    e = enroll(client, dt.date(2026, 10, 26))
    log_upper_a(db, e["id"], short=1)
    upper_a = session_view(client.get("/v1/week", params={"week": 1}).json(), "upper_a")
    assert (upper_a["cleared"], upper_a["sets_logged"]) == (False, 22)


def test_arc(client: TestClient, db: Session) -> None:
    start = monday_weeks_ago(db, client, 9)
    e = enroll(client, start)
    body = client.get("/v1/arc").json()
    assert (body["current_week"], body["current_phase_ord"], body["start_date"]) == (9, 2, start.isoformat())
    statuses = [p["status"] for p in body["phases"]]
    assert statuses == ["past", "past", "current"] + ["future"] * 8
    trial1 = body["phases"][2]
    assert (trial1["name"], trial1["start_date"], trial1["end_date"]) == (
        "Trial I",
        (start + dt.timedelta(weeks=9)).isoformat(),
        (start + dt.timedelta(weeks=9, days=6)).isoformat(),
    )
    assert body["progress"]["sessions_required"] == 0  # a Trial week
    assert e["id"]


def test_arc_progress_in_a_training_week(client: TestClient, db: Session) -> None:
    start = monday_weeks_ago(db, client, 1)
    e = enroll(client, start)
    log_upper_a(db, e["id"])
    progress = client.get("/v1/arc").json()["progress"]
    assert progress == {
        "week": 1,
        "week_in_phase": 1,
        "weeks_in_phase": 8,
        "sessions_cleared": 1,
        "sessions_required": 5,
    }


def test_arc_before_start(client: TestClient, db: Session) -> None:
    enroll(client, monday_weeks_ago(db, client, -2))
    body = client.get("/v1/arc").json()
    assert (body["current_week"], body["current_phase_ord"], body["progress"]) == (-2, None, None)
    assert all(p["status"] == "future" for p in body["phases"])


def test_other_users_sessions_are_not_counted(client: TestClient, db: Session) -> None:
    e = enroll(client, dt.date(2026, 10, 26))
    log_upper_a(db, e["id"])
    other = client.post(
        "/v1/enrollments",
        json={"path_slug": "storm", "start_date": "2026-10-26"},
        headers={"X-Dev-User": "o@x.io"},
    )
    assert other.status_code == 201
    body = client.get("/v1/week", params={"week": 1}, headers={"X-Dev-User": "o@x.io"}).json()
    assert session_view(body, "upper_a")["cleared"] is False
    assert db.scalar(select(Enrollment.id).where(Enrollment.id == uuid.UUID(other.json()["id"])))


def test_path_change_only_affects_sessions_not_yet_started(client: TestClient, db: Session) -> None:
    """M4 acceptance: a logged Upper A keeps its old path's techniques; next week uses the new path."""
    e = enroll(client, dt.date(2026, 10, 26))  # storm
    batch_week = client.get("/v1/week", params={"week": 1}).json()
    upper_a = session_view(batch_week, "upper_a")
    sid = str(uuid.uuid4())
    sets = [
        {
            "client_id": str(uuid.uuid4()),
            "session_client_id": sid,
            "exercise_slug": row["exercise"],
            "set_no": n,
            "weight_lb": 50,
            "reps": row["rep_max"],
            "logged_at": f"2026-11-02T07:{i:02d}:00Z",
        }
        for i, (row, n) in enumerate(
            (r, n) for r in upper_a["prescriptions"] for n in range(1, r["sets"] + 1)
        )
    ]
    session = {"client_id": sid, "template_code": "upper_a", "week": 1, "started_at": "2026-11-02T07:00:00Z"}
    assert client.post("/v1/sync", json={"sessions": [session], "sets": sets}).json()["sessions"][0][
        "cleared"
    ]

    client.patch(f"/v1/enrollments/{e['id']}", json={"path_slug": "shadow"})
    week1 = session_view(client.get("/v1/week", params={"week": 1}).json(), "upper_a")
    week2 = session_view(client.get("/v1/week", params={"week": 2}).json(), "upper_a")
    techniques = lambda s: [r["exercise"] for r in s["prescriptions"] if r["is_path_technique"]]  # noqa: E731
    assert week1["cleared"] is True
    assert techniques(week1) == ["cable-lateral-raise-drop-set", "behind-the-back-shrug"]  # storm, as logged
    assert techniques(week2) == ["pistol-squat-progression", "l-sit-hold"]  # shadow from now on
    assert client.get("/v1/me").json()["stats"]["sessions_cleared"] == 1


def test_technique_steps_current_step_and_ready_to_advance(client: TestClient) -> None:
    enroll(client, dt.date(2026, 10, 26), path="shadow")
    view = session_view(client.get("/v1/week", params={"week": 1}).json(), "upper_a")
    pistol = next(r for r in view["prescriptions"] if r["exercise"] == "pistol-squat-progression")
    assert [s["name"] for s in pistol["steps"]] == [
        "Box pistol",
        "Assisted pistol",
        "Counterweight pistol",
        "Full pistol",
    ]
    assert (pistol["current_step"], pistol["ready_to_advance"]) == ("box-pistol-squat", False)
    plain = next(r for r in view["prescriptions"] if r["exercise"] == "incline-dumbbell-press")
    assert (plain["steps"], plain["current_step"]) == ([], None)

    # Log the whole session with box pistols at the top of the range (3 x 5): ready for the next step.
    sid = str(uuid.uuid4())
    rows = [(r, n) for r in view["prescriptions"] for n in range(1, r["sets"] + 1)]
    sets = [
        {
            "client_id": str(uuid.uuid4()),
            "session_client_id": sid,
            "exercise_slug": "box-pistol-squat"
            if r["exercise"] == "pistol-squat-progression"
            else r["exercise"],
            "set_no": n,
            "weight_lb": 0,
            "reps": r["rep_max"],
            "logged_at": f"2026-11-02T07:{i:02d}:00Z",
        }
        for i, (r, n) in enumerate(rows)
    ]
    session = {"client_id": sid, "template_code": "upper_a", "week": 1, "started_at": "2026-11-02T07:00:00Z"}
    out = client.post("/v1/sync", json={"sessions": [session], "sets": sets}).json()
    assert out["sessions"][0]["cleared"] is True  # sets on a step clear the technique row
    after = session_view(client.get("/v1/week", params={"week": 2}).json(), "upper_a")
    pistol = next(r for r in after["prescriptions"] if r["exercise"] == "pistol-squat-progression")
    assert (pistol["current_step"], pistol["ready_to_advance"]) == ("box-pistol-squat", True)
