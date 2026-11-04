"""Workbook import, export and account deletion (issue #26), including the M2 acceptance check."""

import io
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.services.deletion  # noqa: F401 - registers delete_user
from app.api.account import user_tables
from app.config import REPO_ROOT
from app.jobs import run_once
from app.models import Base, User
from tests.conftest import DEV_USER

FIXTURES = REPO_ROOT / "fixtures"
TEMPLATE = FIXTURES / "Ki_Forge_Training_Log_TEMPLATE.xlsx"
PERSONAL = sorted(FIXTURES.glob("joe_*.xlsx"))
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
GOLDEN_TESTS = (8, 30, 510, 115, 185, 245, 190, 45.5, 34)


def upload(client: TestClient, data: bytes, commit: bool = False, status: int = 200) -> dict:
    r = client.post(
        "/v1/import/workbook",
        params={"commit": str(commit).lower()},
        files={"file": ("log.xlsx", data, XLSX)},
    )
    assert r.status_code == status, r.text
    return r.json()


def filled_workbook() -> bytes:
    """The template with Week 1 Upper A at top reps and a complete Trial 0 (saved by openpyxl: no cache)."""
    wb = openpyxl.load_workbook(TEMPLATE)
    cached = openpyxl.load_workbook(TEMPLATE, data_only=True)["Log"]  # technique rows' H is a formula
    log = wb["Log"]
    for r in range(2, 10):
        sets, top = cached[f"H{r}"].value, cached[f"I{r}"].value or 12
        log[f"J{r}"] = 50
        for col in "KLMN"[:sets]:
            log[f"{col}{r}"] = top
    for row, v in zip(range(3, 12), GOLDEN_TESTS, strict=True):
        wb["Tests"][f"C{row}"] = v
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_template_dry_run(client: TestClient) -> None:
    out = upload(client, TEMPLATE.read_bytes())
    assert (out["committed"], out["sessions"], out["sets"], out["stats"]) == (False, 0, 0, None)
    assert out["computed"]["total_xp"] == 0
    assert out["workbook"]["total_xp"] == 0 and out["workbook"]["rank"] == "Rookie"
    assert out["mismatches"] == []
    assert client.get("/v1/me").json()["enrollment"] is None  # dry run writes nothing


def test_template_commit_is_zero(client: TestClient) -> None:
    out = upload(client, TEMPLATE.read_bytes(), commit=True)
    assert out["committed"] is True
    assert (out["stats"]["total_xp"], out["stats"]["sessions_cleared"]) == (0, 0)
    me = client.get("/v1/me").json()
    assert (me["enrollment"]["path_slug"], me["enrollment"]["start_date"]) == ("storm", "2026-10-26")


def test_filled_workbook_commit_matches_m1_totals(client: TestClient) -> None:
    data = filled_workbook()
    out = upload(client, data, commit=True)
    assert out["workbook"] is None and out["mismatches"] == []  # no cached values to compare
    computed = out["computed"]
    assert (
        computed["total_xp"],
        computed["level"],
        computed["power_level"],
        computed["sessions_cleared"],
    ) == (
        740,
        2,
        549,
        1,
    )
    stats = client.get("/v1/me").json()["stats"]
    assert stats["total_xp"] == 740 + 75  # + First Blood: badges are app-only, not in the workbook
    assert (stats["power_level"], stats["frame_ratio"], stats["sessions_cleared"]) == (549, 1.34, 1)

    again = upload(client, data, commit=True)
    assert again["xp_awarded"] == []
    assert client.get("/v1/me").json()["stats"] == stats


@pytest.mark.skipif(not PERSONAL, reason="no fixtures/joe_*.xlsx (personal workbook is gitignored)")
@pytest.mark.parametrize("path", PERSONAL, ids=[p.name for p in PERSONAL])
def test_m2_acceptance_personal_workbook(client: TestClient, path: Path) -> None:
    out = upload(client, path.read_bytes(), commit=True)
    assert all(m["explained"] for m in out["mismatches"]), out["mismatches"]
    computed = out["computed"]
    stats = client.get("/v1/me").json()["stats"]
    badge_xp = sum(a["amount"] for a in out["xp_awarded"] if a["type"] == "badge")
    assert stats["total_xp"] == computed["total_xp"] + badge_xp
    for key in ("power_level", "frame_ratio", "sessions_cleared"):
        assert stats[key] == computed[key], key
    assert upload(client, path.read_bytes(), commit=True)["xp_awarded"] == []


def test_import_into_a_different_run_is_rejected(client: TestClient) -> None:
    client.post("/v1/enrollments", json={"path_slug": "shadow", "start_date": "2026-10-26"})
    out = upload(client, TEMPLATE.read_bytes(), commit=True, status=409)
    assert out["error"]["code"] == "enrollment_mismatch"


def test_invalid_file(client: TestClient) -> None:
    assert upload(client, b"not a spreadsheet", status=422)["error"]["code"] == "invalid_workbook"


# --- export and delete -----------------------------------------------------------------------------------


def test_user_tables_cover_every_user_owned_table() -> None:
    owned = {t.name for t in Base.metadata.tables.values() if "user_id" in t.columns} | {"users", "set_logs"}
    assert set(user_tables()) == owned


def test_export(client: TestClient) -> None:
    upload(client, filled_workbook(), commit=True)
    client.post("/v1/scans", json={"shoulders_in": 46, "waist_in": 33})
    client.get("/v1/me", headers={"X-Dev-User": "someone@else.io"})
    out = client.get("/v1/export").json()
    tables = out["tables"]
    assert set(tables) == set(user_tables())
    assert [u["email"] for u in tables["users"]] == [DEV_USER]
    assert len(tables["set_logs"]) == 23
    assert len(tables["test_results"]) == 9
    assert len(tables["body_scans"]) == 1
    assert sum(e["amount"] for e in tables["xp_events"]) == client.get("/v1/me").json()["stats"]["total_xp"]


@pytest.fixture
def scope(db: Session):
    @contextmanager
    def _scope() -> Iterator[Session]:
        yield db

    return _scope


def test_delete_account(client: TestClient, db: Session, scope) -> None:
    upload(client, filled_workbook(), commit=True)
    uid = db.scalar(select(User.id).where(User.email == DEV_USER))
    r = client.delete("/v1/me")
    assert (r.status_code, r.json()["status"]) == (202, "scheduled")
    assert client.get("/v1/me").status_code == 401  # signed out at once
    while run_once(scope):
        pass
    db.expire_all()
    for table in Base.metadata.sorted_tables:
        if "user_id" in table.columns:
            assert db.scalar(select(func.count()).select_from(table).where(table.c.user_id == uid)) == 0, (
                table.name
            )
    assert db.get(User, uid) is None
    fresh = client.get("/v1/me").json()  # the same email can start over afterwards
    assert fresh["stats"]["total_xp"] == 0


def test_m4_acceptance_export_round_trips_through_import(client: TestClient) -> None:
    """M4 acceptance: export JSON round-trips through import on a fresh user with equal totals."""
    upload(client, filled_workbook(), commit=True)  # a cleared Upper A + a complete Trial 0
    client.post("/v1/scans", json={"shoulders_in": 46, "waist_in": 33, "taken_at": "2026-11-20T08:00:00Z"})
    original = client.get("/v1/me").json()
    export = client.get("/v1/export").json()

    fresh = {"X-Dev-User": "restored@example.com"}
    r = client.post("/v1/import/export", json=export, headers=fresh)
    assert r.status_code == 200, r.text
    restored = client.get("/v1/me", headers=fresh).json()
    assert restored["stats"] == original["stats"]
    assert sorted(b["slug"] for b in restored["badges"]) == sorted(b["slug"] for b in original["badges"])
    assert restored["enrollment"]["path_slug"] == original["enrollment"]["path_slug"]

    # Idempotent and only into a fresh account.
    assert client.post("/v1/import/export", json=export, headers=fresh).status_code == 409
    assert client.post("/v1/import/export", json=export).status_code == 409
