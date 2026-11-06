"""Request dependencies: database session and the signed-in user.

Sign-in is Clerk (#78): the app sends `Authorization: Bearer <Clerk session token>`, and the user row is
found by Clerk user id (`users.auth_id`). The first Clerk sign-in links an existing dev account with
the same verified email, so history logged before registration carries over.

The local dev header `X-Dev-User: <email>` still works, but only when APP_ENV is local or test.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.config import settings
from app.db import get_session
from app.models import User
from app.services import auth

DEV_AUTH_ENVS = frozenset({"local", "test"})
DEV_PREFIX = "dev:"

Db = Annotated[Session, Depends(get_session)]


def _dev_email(raw: str | None) -> str:
    if settings.app_env not in DEV_AUTH_ENVS:
        raise ApiError(401, "unauthorized", "sign-in required")
    if not raw:
        raise ApiError(401, "unauthorized", "sign-in required (or X-Dev-User for local dev)")
    email = raw.strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email:
        raise ApiError(401, "unauthorized", "X-Dev-User must be an email address")
    return email


def _create(db: Session, auth_id: str, email: str | None) -> User | None:
    db.execute(
        insert(User)
        .values(auth_id=auth_id, email=email, display_name=(email or "athlete").split("@")[0])
        .on_conflict_do_nothing(index_elements=[User.auth_id])
    )
    db.commit()
    return db.scalar(select(User).where(User.auth_id == auth_id))


def _dev_user(db: Session, raw: str | None) -> User | None:
    email = _dev_email(raw)
    user = db.scalar(select(User).where(User.auth_id == f"{DEV_PREFIX}{email}"))
    # An account that has since signed in with Clerk keeps working through the dev header locally.
    user = user or db.scalar(select(User).where(User.email == email))
    return user or _create(db, f"{DEV_PREFIX}{email}", email)


def _clerk_user(db: Session, token: str) -> User | None:
    try:
        clerk_id = auth.verify_session(token)
    except auth.AuthUnavailable:
        raise ApiError(503, "auth_unavailable", "sign-in isn't configured on this server") from None
    except auth.InvalidToken as e:
        raise ApiError(401, "unauthorized", f"sign-in expired or invalid: {e}") from None

    user = db.scalar(select(User).where(User.auth_id == clerk_id))
    if user is not None:
        return user
    email = auth.verified_email(clerk_id)
    if email:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            if not existing.auth_id.startswith(DEV_PREFIX):
                # The email already belongs to another Clerk account; never merge two real accounts.
                raise ApiError(409, "email_in_use", "this email is already linked to another account")
            existing.auth_id = clerk_id  # first Clerk sign-in: keep the history logged before registration
            db.commit()
            return existing
    return _create(db, clerk_id, email)


def current_user(
    db: Db,
    authorization: Annotated[str | None, Header()] = None,
    x_dev_user: Annotated[str | None, Header()] = None,
) -> User:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        user = _clerk_user(db, token.strip())
    else:
        user = _dev_user(db, x_dev_user)
    if user is None or user.deleted_at is not None:
        raise ApiError(401, "unauthorized", "account is being deleted")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
