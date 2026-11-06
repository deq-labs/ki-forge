"""Clerk sign-in (#78): bearer tokens, linking a dev account by verified email, dev header rules, deletion.

Clerk itself is replaced by fakes: `verify_session` maps a token to a Clerk user id and `verified_email`
returns that user's verified email.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.services.deletion  # noqa: F401 - registers delete_user
from app.config import settings
from app.db import get_session
from app.jobs import run_once
from app.main import app
from app.models import User
from app.services import auth

# token -> (clerk user id, verified email or None)
ACCOUNTS = {
    "tok-joe": ("user_joe", "joe@example.com"),
    "tok-new": ("user_new", "new@example.com"),
    "tok-phone": ("user_phone", None),
    "tok-other": ("user_other", "joe@example.com"),
}


@pytest.fixture
def clerk(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    deleted: list[str] = []

    def verify(token: str) -> str:
        if token not in ACCOUNTS:
            raise auth.InvalidToken("bad signature")
        return ACCOUNTS[token][0]

    def email(clerk_id: str) -> str | None:
        return next(e for cid, e in ACCOUNTS.values() if cid == clerk_id)

    monkeypatch.setattr(auth, "verify_session", verify)
    monkeypatch.setattr(auth, "verified_email", email)
    monkeypatch.setattr(auth, "delete_clerk_user", deleted.append)
    monkeypatch.setattr(settings, "clerk_secret_key", "sk_test_fake")
    return deleted


@pytest.fixture
def anon(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_new_clerk_user_is_created(anon: TestClient, db: Session, clerk: list[str]) -> None:
    me = anon.get("/v1/me", headers=bearer("tok-new"))
    assert me.status_code == 200, me.text
    user = db.scalar(select(User).where(User.auth_id == "user_new"))
    assert user is not None and user.email == "new@example.com"
    assert anon.get("/v1/me", headers=bearer("tok-new")).json()["user"]["id"] == str(user.id)  # found again


def test_first_sign_in_links_the_dev_account(anon: TestClient, db: Session, clerk: list[str]) -> None:
    dev = anon.get("/v1/me", headers={"X-Dev-User": "Joe@Example.com"}).json()
    linked = anon.get("/v1/me", headers=bearer("tok-joe")).json()
    assert linked["user"]["id"] == dev["user"]["id"]  # same row, history kept
    assert db.scalar(select(User.auth_id).where(User.email == "joe@example.com")) == "user_joe"
    # Locally the dev header still reaches the linked account.
    assert (
        anon.get("/v1/me", headers={"X-Dev-User": "joe@example.com"}).json()["user"]["id"]
        == dev["user"]["id"]
    )


def test_never_merges_two_clerk_accounts(anon: TestClient, clerk: list[str]) -> None:
    assert anon.get("/v1/me", headers=bearer("tok-joe")).status_code == 200
    r = anon.get("/v1/me", headers=bearer("tok-other"))
    assert (r.status_code, r.json()["error"]["code"]) == (409, "email_in_use")


def test_user_without_email(anon: TestClient, db: Session, clerk: list[str]) -> None:
    assert anon.get("/v1/me", headers=bearer("tok-phone")).status_code == 200
    assert db.scalar(select(User.email).where(User.auth_id == "user_phone")) is None


def test_bad_or_missing_token(anon: TestClient, clerk: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    r = anon.get("/v1/me", headers=bearer("forged"))
    assert (r.status_code, r.json()["error"]["code"]) == (401, "unauthorized")
    monkeypatch.setattr(settings, "app_env", "production")
    assert anon.get("/v1/me").status_code == 401
    # Production never accepts the dev header.
    assert anon.get("/v1/me", headers={"X-Dev-User": "joe@example.com"}).status_code == 401
    assert anon.get("/v1/me", headers=bearer("tok-joe")).status_code == 200


def test_server_without_clerk(anon: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "clerk_secret_key", "")
    r = anon.get("/v1/me", headers=bearer("anything"))
    assert (r.status_code, r.json()["error"]["code"]) == (503, "auth_unavailable")


def test_delete_account_deletes_the_clerk_user(anon: TestClient, db: Session, clerk: list[str]) -> None:
    anon.get("/v1/me", headers=bearer("tok-new"))
    assert anon.delete("/v1/me", headers=bearer("tok-new")).status_code == 202

    @contextmanager
    def scope() -> Iterator[Session]:
        yield db

    while run_once(scope):
        pass
    assert clerk == ["user_new"]
    assert db.scalar(select(User).where(User.auth_id == "user_new")) is None


def test_dev_accounts_are_not_sent_to_clerk(anon: TestClient, db: Session, clerk: list[str]) -> None:
    anon.get("/v1/me", headers={"X-Dev-User": "solo@example.com"})
    anon.delete("/v1/me", headers={"X-Dev-User": "solo@example.com"})

    @contextmanager
    def scope() -> Iterator[Session]:
        yield db

    while run_once(scope):
        pass
    assert clerk == []
