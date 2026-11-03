"""Trials and tape scans (issue #24)."""

import pytest
from fastapi.testclient import TestClient

GOLDEN = {
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


@pytest.fixture
def run(client: TestClient) -> dict:
    r = client.post("/v1/enrollments", json={"path_slug": "storm", "start_date": "2026-10-26"})
    assert r.status_code == 201
    return r.json()


def put(client: TestClient, ord_: int, results: dict, status: int = 200, **extra) -> dict:
    r = client.put(f"/v1/trials/{ord_}", json={"results": results, **extra})
    assert r.status_code == status, r.text
    return r.json()


def test_golden_full_trial(client: TestClient, run: dict) -> None:
    out = put(client, 0, GOLDEN, taken_on="2026-10-26")
    assert (out["complete"], out["power_level"], out["frame_ratio"]) == (True, 549, 1.34)
    assert out["xp_awarded"] == [
        {"type": "trial_completed", "amount": 500, "source_id": f"trial:{run['id']}:0"}
    ]
    assert out["level_up"] == {"from": 1, "to": 2, "rank": "Rookie"}
    assert (out["stats"]["total_xp"], out["stats"]["power_level"], out["stats"]["frame_ratio"]) == (
        500,
        549,
        1.34,
    )
    assert out["name"] == "Trial 0"


def test_full_trial_awards_once(client: TestClient, run: dict) -> None:
    put(client, 0, GOLDEN)
    again = put(client, 0, GOLDEN)
    assert again["xp_awarded"] == [] and again["level_up"] is None
    assert again["stats"]["total_xp"] == 500
    changed = put(client, 0, {"pullups_max": 9})  # editing a complete Trial does not re-award
    assert changed["xp_awarded"] == []
    assert changed["power_level"] == 554


def test_partial_trial_awards_nothing(client: TestClient, run: dict) -> None:
    partial = {k: v for k, v in GOLDEN.items() if k not in ("shoulders_in", "waist_in")}
    out = put(client, 0, partial)
    assert (out["complete"], out["xp_awarded"], out["frame_ratio"]) == (False, [], None)
    assert out["power_level"] == 549 - 340
    assert out["results"]["shoulders_in"] is None
    done = put(client, 0, {"shoulders_in": 45.5, "waist_in": 34})
    assert done["complete"] is True
    assert [a["amount"] for a in done["xp_awarded"]] == [500]


def test_null_clears_a_value(client: TestClient, run: dict) -> None:
    put(client, 0, GOLDEN)
    out = put(client, 0, {"waist_in": None})
    assert (out["results"]["waist_in"], out["frame_ratio"], out["complete"]) == (None, None, False)


@pytest.mark.parametrize(("ord_", "status", "code"), [(1, 404, "not_found"), (99, 404, "not_found")])
def test_only_trial_phases(client: TestClient, run: dict, ord_: int, status: int, code: str) -> None:
    assert put(client, ord_, {"pullups_max": 1}, status)["error"]["code"] == code


def test_unknown_test_and_bad_values(client: TestClient, run: dict) -> None:
    assert put(client, 0, {"bench_press": 225}, 422)["error"]["code"] == "unknown_test"
    assert put(client, 0, {"pullups_max": -1}, 422)["error"]["code"] == "validation_error"


def test_list_trials(client: TestClient, run: dict) -> None:
    put(client, 2, {"pullups_max": 10})
    trials = client.get("/v1/trials").json()
    assert [t["phase_ord"] for t in trials] == [0, 2, 4, 6, 8, 10]
    assert [t["name"] for t in trials] == [
        "Trial 0",
        "Trial I",
        "Trial II",
        "Trial III",
        "Trial IV",
        "Final Trial",
    ]
    assert trials[1]["start_date"] == "2026-12-28"  # week 9
    assert trials[1]["results"]["pullups_max"] == 10 and trials[1]["power_level"] == 50
    assert trials[0]["power_level"] is None
    assert client.get("/v1/me").json()["stats"]["power_level"] == 50  # latest Trial with tests


def test_trials_need_enrollment(client: TestClient) -> None:
    assert client.get("/v1/trials").status_code == 404
    assert client.post("/v1/scans", json={"shoulders_in": 45, "waist_in": 34}).status_code == 404


# --- scans -----------------------------------------------------------------------------------------------


def test_tape_scan(client: TestClient, run: dict) -> None:
    r = client.post(
        "/v1/scans", json={"shoulders_in": 46, "waist_in": 33, "taken_at": "2026-11-20T08:00:00Z"}
    )
    assert r.status_code == 201
    out = r.json()
    assert (out["scan"]["frame_ratio"], out["scan"]["status"], out["upload_url"]) == (1.39, "done", None)
    assert sorted(a["type"] for a in out["xp_awarded"]) == ["badge", "scan_logged"]
    assert [b["slug"] for b in out["new_badges"]] == ["power-reading"]
    assert out["stats"]["total_xp"] == 50 + 75


def test_latest_frame_ratio_from_trial_or_scan(client: TestClient, run: dict) -> None:
    put(client, 0, GOLDEN, taken_on="2026-10-26")
    client.post("/v1/scans", json={"shoulders_in": 46, "waist_in": 33, "taken_at": "2026-11-20T08:00:00Z"})
    assert client.get("/v1/me").json()["stats"]["frame_ratio"] == 1.39
    put(client, 2, {"shoulders_in": 47, "waist_in": 33}, taken_on="2026-12-28")
    assert client.get("/v1/me").json()["stats"]["frame_ratio"] == 1.42


def test_golden_frame_badge(client: TestClient, run: dict) -> None:
    out = client.post("/v1/scans", json={"shoulders_in": 48, "waist_in": 30}).json()  # 1.60 = Storm target
    assert "golden-frame" in [b["slug"] for b in out["new_badges"]]


def test_list_scans_newest_first(client: TestClient, run: dict) -> None:
    for day in ("2026-11-01", "2026-11-15", "2026-11-08"):
        client.post("/v1/scans", json={"shoulders_in": 46, "waist_in": 33, "taken_at": f"{day}T08:00:00Z"})
    scans = client.get("/v1/scans").json()
    assert [s["taken_at"][:10] for s in scans] == ["2026-11-15", "2026-11-08", "2026-11-01"]
    other = client.get("/v1/scans", headers={"X-Dev-User": "o@x.io"}).json()
    assert other == []


def test_photo_scans_not_available_yet(client: TestClient, run: dict) -> None:
    r = client.post("/v1/scans", json={"shoulders_in": 46, "waist_in": 33, "with_photo": True})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "photo_scans_unavailable")


@pytest.mark.parametrize("body", [{"shoulders_in": 46}, {"shoulders_in": 0, "waist_in": 30}, {}])
def test_scan_needs_both_measurements(client: TestClient, run: dict, body: dict) -> None:
    assert client.post("/v1/scans", json=body).status_code == 422
