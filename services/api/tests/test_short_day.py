"""Short day and End early (#81): the rules engine's short build, sync, and the week view."""

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient

from app.rules.calendar import phase_for
from app.rules.program import Program
from app.rules.sessions import build_session
from tests.test_calendar_api import enroll, session_view

START = dt.date(2026, 10, 26)
T0 = dt.datetime(2026, 10, 26, 6, 0, tzinfo=dt.UTC)


def build(program: Program, code: str, week: int = 0, *, short: bool, path: str = "iron-tempo"):
    p = program.for_path(path)
    phase = phase_for(week, p)
    assert phase is not None
    return build_session(p, p.template(code), phase, program.path(path), short_day=short)


# --- rules -----------------------------------------------------------------------------------------------


def test_short_day_drops_the_program_roles(program: Program) -> None:
    full = build(program, "it_pull", short=False)
    short = build(program, "it_pull", short=True)
    assert [i.role for i in full.items] == ["main", "finisher", "accessory", "core", "x3", "x3"]
    assert [i.role for i in short.items] == ["main", "accessory"]
    assert short.sets_needed == 7 + 4  # EMOM rounds + DB rows


def test_short_day_on_a_deload_week(program: Program) -> None:
    short = build(program, "it_pull", week=4, short=True)
    assert [(i.role, i.sets) for i in short.items] == [("main", 4), ("accessory", 4)]


def test_programs_without_a_short_day_ignore_it(program: Program) -> None:
    assert program.short_day is None
    full = build(program, "upper_a", short=False, path="storm")
    assert build(program, "upper_a", short=True, path="storm") == full


# --- API -------------------------------------------------------------------------------------------------


@pytest.fixture
def run(client: TestClient) -> dict:
    return enroll(client, START, path="iron-tempo")


def _pull_sets(client: TestClient, sid: str, roles: set[str]) -> list[dict]:
    """Every set of the pull day's rows with these roles, at their targets."""
    pull = session_view(client.get("/v1/week", params={"week": 0}).json(), "it_pull")
    sets: list[dict] = []

    def add(exercise: str, n: int, reps: int, slot: str | None) -> None:
        sets.append(
            {
                "client_id": str(uuid.uuid4()),
                "session_client_id": sid,
                "exercise_slug": exercise,
                "set_no": n,
                "reps": reps,
                "slot": slot,
                "logged_at": (T0 + dt.timedelta(minutes=len(sets))).isoformat(),
            }
        )

    for row in pull["prescriptions"]:
        if row["role"] not in roles:
            continue
        for n in range(1, row["sets"] + 1):
            if row["block"]:
                for m in row["block"]["movements"]:
                    add(m["levels"][0]["exercise"], n, m["levels"][0]["amount"] or 1, row["key"])
            else:
                add(row["exercise"], n, row["rep_max"], None)
    return sets


def _session(sid: str, **extra) -> dict:
    return {"client_id": sid, "template_code": "it_pull", "week": 0, "started_at": T0.isoformat(), **extra}


def test_week_offers_the_short_day(client: TestClient, run: dict) -> None:
    body = client.get("/v1/week", params={"week": 0}).json()
    pull = session_view(body, "it_pull")
    assert pull["short_day_roles"] == ["finisher", "core", "x3"]
    assert (pull["short_day"], pull["ended"]) == (False, False)
    assert pull["short_day_note"].startswith("Short day")
    # The pump day has none of those roles: no short version.
    assert session_view(body, "it_pump")["short_day_roles"] == []
    # Car in: the calisthenics twin has core and X3 work but no finisher.
    assert session_view(body, "it_engine")["short_day_roles"] == ["finisher", "x3"]


def test_a_finished_short_day_clears(client: TestClient, run: dict) -> None:
    sid = str(uuid.uuid4())
    batch = {
        "sessions": [_session(sid, short_day=True)],
        "sets": _pull_sets(client, sid, {"main", "accessory"}),
    }
    out = client.post("/v1/sync", json=batch)
    assert out.status_code == 200, out.text
    assert out.json()["sessions"][0]["cleared"]
    pull = session_view(client.get("/v1/week", params={"week": 0}).json(), "it_pull")
    assert (pull["short_day"], pull["cleared"], pull["sets_needed"], pull["sets_logged"]) == (
        True,
        True,
        11,
        11,
    )
    assert len(pull["prescriptions"]) == 6  # the full day is still sent, so the switch works offline


def test_switching_back_to_full_needs_the_rest(client: TestClient, run: dict) -> None:
    sid = str(uuid.uuid4())
    sets = _pull_sets(client, sid, {"main", "accessory"})
    assert (
        client.post("/v1/sync", json={"sessions": [_session(sid)], "sets": sets}).json()["sessions"][0][
            "cleared"
        ]
        is False
    )
    # Switched to short later: the same sets now clear it.
    out = client.post("/v1/sync", json={"sessions": [_session(sid, short_day=True)], "sets": []})
    assert out.json()["sessions"][0]["cleared"] is True
    # An older client that doesn't send the flag leaves it alone.
    assert client.post("/v1/sync", json={"sessions": [_session(sid)], "sets": []}).json()["sessions"][0][
        "cleared"
    ]


def test_end_early_keeps_xp_but_does_not_clear(client: TestClient, run: dict) -> None:
    sid = str(uuid.uuid4())
    done = T0 + dt.timedelta(hours=1)
    batch = {
        "sessions": [_session(sid, completed_at=done.isoformat())],
        "sets": _pull_sets(client, sid, {"main"}),
    }
    body = client.post("/v1/sync", json=batch).json()
    assert body["sessions"][0]["cleared"] is False
    assert sum(a["amount"] for a in body["xp_awarded"] if a["type"] == "set_logged") == 7 * 5
    pull = session_view(client.get("/v1/week", params={"week": 0}).json(), "it_pull")
    assert (pull["ended"], pull["cleared"], pull["sets_logged"]) == (True, False, 7)


def test_ending_early_as_a_short_day_clears(client: TestClient, run: dict) -> None:
    sid = str(uuid.uuid4())
    done = (T0 + dt.timedelta(hours=1)).isoformat()
    batch = {
        "sessions": [_session(sid, completed_at=done, short_day=True)],
        "sets": _pull_sets(client, sid, {"main", "accessory"}),
    }
    assert client.post("/v1/sync", json=batch).json()["sessions"][0]["cleared"]
    pull = session_view(client.get("/v1/week", params={"week": 0}).json(), "it_pull")
    assert (pull["ended"], pull["cleared"]) == (False, True)
