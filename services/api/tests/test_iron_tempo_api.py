"""Iron Tempo over the API: enrolling, 1RMs, block weeks and syncing a block session (#65)."""

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Enrollment, ProgramRow
from tests.test_calendar_api import enroll, monday_weeks_ago, session_view

START = dt.date(2026, 10, 26)
T0 = dt.datetime(2026, 10, 26, 6, 0, tzinfo=dt.UTC)

ONE_RMS = {
    "conventional-deadlift": 305,
    "standing-barbell-overhead-press": 135,
    "barbell-back-squat": 255,
    "front-squat": 205,
}


@pytest.fixture
def run(client: TestClient) -> dict:
    return enroll(client, START, path="iron-tempo")


def test_enrolls_on_the_block_program(client: TestClient, db: Session, run: dict) -> None:
    e = db.get(Enrollment, uuid.UUID(run["id"]))
    assert db.get(ProgramRow, e.program_id).slug == "iron-tempo"
    assert run["path_slug"] == "iron-tempo"


def test_lifts_round_trip(client: TestClient, run: dict) -> None:
    body = client.get("/v1/me/lifts").json()
    assert [(x["exercise"], x["one_rm_lb"]) for x in body["lifts"]] == [(k, None) for k in ONE_RMS]
    body = client.put("/v1/me/lifts", json={"lifts": ONE_RMS}).json()
    assert {x["exercise"]: x["one_rm_lb"] for x in body["lifts"]} == ONE_RMS
    assert all(x["updated_at"] for x in body["lifts"])
    body = client.put("/v1/me/lifts", json={"lifts": {"front-squat": None}}).json()
    assert {x["exercise"]: x["one_rm_lb"] for x in body["lifts"]}["front-squat"] is None


@pytest.mark.parametrize(
    "lifts",
    [{"pull-up": 100}, {"front-squat": 0}, {"front-squat": 5000}],
)
def test_lifts_validation(client: TestClient, run: dict, lifts: dict) -> None:
    r = client.put("/v1/me/lifts", json={"lifts": lifts})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "validation_error")


def test_week_shows_blocks_with_loads_from_1rms(client: TestClient, run: dict) -> None:
    body = client.get("/v1/week", params={"week": 0}).json()
    assert body["phase"]["name"] == "Build" and body["phase"]["block"] == 1
    assert [s["code"] for s in body["sessions"]] == ["it_pull", "it_push", "it_legs", "it_engine", "it_pump"]
    assert body["lifts_needed"] == list(ONE_RMS)  # front squat is used by Thursday's finisher

    client.put("/v1/me/lifts", json={"lifts": ONE_RMS})
    body = client.get("/v1/week", params={"week": 0}).json()
    assert body["lifts_needed"] == []
    pull = session_view(body, "it_pull")
    assert pull["garage_twin"] and pull["warmup"].startswith("3 rounds")
    emom = pull["prescriptions"][0]
    assert (emom["key"], emom["role"], emom["sets"], emom["prefill_weight_lb"]) == ("p0", "main", 7, None)
    deadlift = emom["block"]["movements"][0]
    # 75 / 80 / 85% of 305 → 228.75 / 244 / 259.25 → nearest 10 lb (the deadlift's increment)
    assert [lv["weight_lb"] for lv in deadlift["levels"]] == [230, 240, 260]
    push_press = session_view(body, "it_push")["prescriptions"][1]["block"]["movements"][0]
    assert (push_press["levels"][0]["percent"], push_press["levels"][0]["weight_lb"]) == (
        80,
        110,
    )  # of strict
    engine = session_view(body, "it_engine")["prescriptions"][0]["block"]["movements"][0]
    assert [lv["exercise"] for lv in engine["levels"]] == [
        "pull-up",
        "chest-to-bar-pull-up",
        "chest-to-bar-pull-up",
    ]


def test_deload_week_and_wrap(client: TestClient, run: dict) -> None:
    deload = client.get("/v1/week", params={"week": 4}).json()
    assert deload["phase"]["name"] == "Deload" and deload["phase"]["deload_note"]
    assert session_view(deload, "it_pull")["prescriptions"][0]["sets"] == 4
    nxt = client.get("/v1/week", params={"week": 5}).json()
    assert (nxt["phase"]["name"], nxt["phase"]["block"]) == ("Build", 2)


def test_garage_day_is_the_car_in_twin(client: TestClient) -> None:
    enroll(client, START, path="iron-tempo", garage=True)
    pull = session_view(client.get("/v1/week", params={"week": 0}).json(), "it_pull")
    assert pull["garage_mode"] and pull["name"] == "Pull + Posterior Chain"
    assert [p["exercise"] for p in pull["prescriptions"]][:3] == [
        "weighted-pull-up",
        "chin-up",
        "australian-row",
    ]
    assert all(p["swap"] is None for p in pull["prescriptions"])


def _car_in_pull(client: TestClient) -> dict:
    """Every row of the car-in pull day: straight sets, then core circuit rounds, then X3."""
    pull = session_view(client.get("/v1/week", params={"week": 0}).json(), "it_pull")
    sid, sets = str(uuid.uuid4()), []

    def add(exercise: str, n: int, reps: int, slot: str) -> None:
        sets.append(
            {
                "client_id": str(uuid.uuid4()),
                "session_client_id": sid,
                "exercise_slug": exercise,
                "set_no": n,
                "weight_lb": 0,
                "reps": reps,
                "logged_at": (T0 + dt.timedelta(minutes=len(sets))).isoformat(),
            }
        )

    for row in pull["prescriptions"]:
        if row["block"]:
            for n in range(1, row["sets"] + 1):
                for m in row["block"]["movements"]:
                    add(m["exercise"], n, m["levels"][0]["amount"] or 1, row["key"])
        else:
            for n in range(1, row["sets"] + 1):
                add(row["exercise"], n, row["rep_max"], row["key"])
    session = {
        "client_id": sid,
        "template_code": "it_pull",
        "week": 0,
        "garage_mode": True,
        "started_at": T0.isoformat(),
    }
    return {"sessions": [session], "sets": sets}


def test_sync_a_car_in_day(client: TestClient) -> None:
    enroll(client, START, path="iron-tempo", garage=True)
    out = client.post("/v1/sync", json=_car_in_pull(client))
    assert out.status_code == 200, out.text
    body = out.json()
    (s,) = body["sessions"]
    assert s["cleared"]
    set_xp = sum(a["amount"] for a in body["xp_awarded"] if a["type"] == "set_logged")
    # 4 + 3 + 3 + 3 + 3 straight sets, 3 core rounds (not 9 movements), 2 X3 sets → 21 sets
    assert set_xp == 21 * 5
    pull = session_view(client.get("/v1/week", params={"week": 0}).json(), "it_pull")
    assert (pull["cleared"], pull["sets_logged"], pull["sets_needed"]) == (True, 21, 21)


def test_twin_codes_are_not_session_templates(client: TestClient, run: dict) -> None:
    batch = {
        "sessions": [
            {
                "client_id": str(uuid.uuid4()),
                "template_code": "it_pull_in",
                "week": 0,
                "started_at": T0.isoformat(),
            }
        ],
        "sets": [],
    }
    r = client.post("/v1/sync", json=batch)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "unknown_template")
    batch["sessions"][0]["template_code"] = "upper_a"  # the main arc's day, not this run's program
    assert client.post("/v1/sync", json=batch).status_code == 422


def test_switching_program_needs_a_restart(client: TestClient, run: dict) -> None:
    r = client.patch(f"/v1/enrollments/{run['id']}", json={"path_slug": "storm"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "program_change")
    other = enroll_after_restart(client, run)
    r = client.patch(f"/v1/enrollments/{other['id']}", json={"path_slug": "iron-tempo"})
    assert r.status_code == 409


def enroll_after_restart(client: TestClient, run: dict) -> dict:
    assert client.post(f"/v1/enrollments/{run['id']}/end").status_code == 200
    return enroll(client, START, path="storm")


def test_arc_shows_the_current_block(client: TestClient, db: Session) -> None:
    start = monday_weeks_ago(db, client, 6)  # week 6 = block 2, week 2 of Build
    enroll(client, start, path="iron-tempo")
    arc = client.get("/v1/arc").json()
    assert arc["block"] == 2 and arc["current_week"] == 6
    assert [(p["name"], p["start_week"], p["end_week"], p["status"]) for p in arc["phases"]] == [
        ("Build", 5, 8, "current"),
        ("Deload", 9, 9, "future"),
    ]
    assert (arc["progress"]["week_in_phase"], arc["progress"]["sessions_required"]) == (2, 4)


def test_default_week_is_not_capped(client: TestClient, db: Session) -> None:
    start = monday_weeks_ago(db, client, 12)
    enroll(client, start, path="iron-tempo")
    body = client.get("/v1/week").json()
    assert (body["week"], body["phase"]["block"], body["phase"]["name"]) == (12, 3, "Build")


def test_export_round_trips_an_iron_tempo_run(client: TestClient) -> None:
    enroll(client, START, path="iron-tempo", garage=True)
    client.put("/v1/me/lifts", json={"lifts": ONE_RMS})
    assert client.post("/v1/sync", json=_car_in_pull(client)).status_code == 200
    original = client.get("/v1/me").json()
    export = client.get("/v1/export").json()

    fresh = {"X-Dev-User": "restored@example.com"}
    r = client.post("/v1/import/export", json=export, headers=fresh)
    assert r.status_code == 200, r.text
    assert client.get("/v1/me", headers=fresh).json()["stats"] == original["stats"]
    lifts = client.get("/v1/me/lifts", headers=fresh).json()["lifts"]
    assert {x["exercise"]: x["one_rm_lb"] for x in lifts} == ONE_RMS
    week = client.get("/v1/week", params={"week": 0}, headers=fresh).json()
    assert session_view(week, "it_pull")["cleared"]
