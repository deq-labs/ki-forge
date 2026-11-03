"""API foundation: GET /v1/program, dev auth, error envelope (issue #20)."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.api.errors import ApiError, install_error_handlers
from app.config import settings
from app.db import get_session
from app.models import User
from app.rules.program import Program, parse_program
from app.services.program import program_ids

# --- GET /v1/program -------------------------------------------------------------------------------------


def test_program_returns_seed_counts(client: TestClient) -> None:
    r = client.get("/v1/program")
    assert r.status_code == 200
    body = r.json()
    prescriptions = [p for t in body["session_templates"] for p in t["prescriptions"]]
    counts = (
        len(body["exercises"]),
        sum(p["exercise"] != "PATH_CONDITIONING" for p in prescriptions),
        len(body["phases"]),
        len(body["paths"]),
        sum(len(p["techniques"]) for p in body["paths"]),
        len(body["badges"]),
    )
    assert counts == (52, 25, 11, 4, 8, 6)
    assert (body["slug"], body["version"], body["cycle_weeks"]) == ("ki-forge-core", 1, 84)


def test_program_round_trips_into_rules_program(client: TestClient, program: Program) -> None:
    body = client.get("/v1/program").json()
    seed = {
        "program": {k: body[k] for k in ("slug", "version", "name", "cycle_weeks")},
        **{
            k: body[k]
            for k in ("exercises", "phases", "session_templates", "paths", "tests", "badges", "ranks")
        },
    }
    for ph in seed["phases"]:  # the API sends every modifier field; the seed omits unset ones
        ph["modifiers"] = {k: v for k, v in ph["modifiers"].items() if v not in (None, {}, 0)}
    assert parse_program(seed) == program


def test_program_etag_and_304(client: TestClient) -> None:
    first = client.get("/v1/program")
    etag = first.headers["etag"]
    assert etag.startswith('W/"ki-forge-core-v1-')
    again = client.get("/v1/program", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""


def test_program_needs_no_auth(db: Session) -> None:
    from app.main import app

    app.dependency_overrides[get_session] = lambda: db
    try:
        assert TestClient(app).get("/v1/program").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_program_ids_match_seed(db: Session, program: Program) -> None:
    ids = program_ids(db)
    assert set(ids.exercises) == set(program.exercises)
    assert set(ids.templates) == {t.code for t in program.session_templates}
    assert sorted(ids.phases) == list(range(11))
    assert ids.exercise_slug(ids.exercises["dips"]) == "dips"
    assert ids.phase_ord(ids.phases[7]) == 7


# --- dev auth and errors ---------------------------------------------------------------------------------


class Who(BaseModel):
    email: str | None
    display_name: str


@pytest.fixture
def auth_app(db: Session) -> Iterator[TestClient]:
    """A throwaway app with one authenticated route, sharing the real dependencies."""
    a = FastAPI()
    install_error_handlers(a)

    @a.get("/whoami", response_model=Who)
    def whoami(user: CurrentUser) -> User:
        return user

    @a.get("/boom")
    def boom() -> None:
        raise ApiError(409, "conflict", "already exists")

    @a.get("/items/{n}")
    def item(n: int) -> dict:
        return {"n": n}

    a.dependency_overrides[get_session] = lambda: db
    with TestClient(a) as c:
        yield c


def test_dev_user_created_on_first_use(auth_app: TestClient, db: Session) -> None:
    r = auth_app.get("/whoami", headers={"X-Dev-User": "  New.Person@Example.com "})
    assert r.status_code == 200
    assert r.json() == {"email": "new.person@example.com", "display_name": "new.person"}
    auth_app.get("/whoami", headers={"X-Dev-User": "new.person@example.com"})
    count = db.scalar(
        select(func.count()).select_from(User).where(User.auth_id == "dev:new.person@example.com")
    )
    assert count == 1


@pytest.mark.parametrize("header", [None, "", "not-an-email", "a@b", "two words@x.com"])
def test_missing_or_invalid_dev_user_is_401(auth_app: TestClient, header: str | None) -> None:
    headers = {} if header is None else {"X-Dev-User": header}
    r = auth_app.get("/whoami", headers=headers)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("env", ["production", "staging"])
def test_dev_header_refused_outside_local(
    auth_app: TestClient, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setattr(settings, "app_env", env)
    r = auth_app.get("/whoami", headers={"X-Dev-User": "joe@example.com"})
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "unauthorized", "message": "sign-in required"}}


def test_error_envelopes(auth_app: TestClient) -> None:
    assert auth_app.get("/boom").json() == {"error": {"code": "conflict", "message": "already exists"}}
    assert auth_app.get("/boom").status_code == 409
    nf = auth_app.get("/nope")
    assert (nf.status_code, nf.json()["error"]["code"]) == (404, "not_found")
    bad = auth_app.get("/items/abc")
    assert bad.status_code == 422
    err = bad.json()["error"]
    assert err["code"] == "validation_error"
    assert err["message"].startswith("path.n:")
    assert err["details"][0]["loc"] == ["path", "n"]
