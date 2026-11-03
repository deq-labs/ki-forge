"""Request dependencies: database session and the signed-in user.

Until Clerk lands (M6) the only auth is the local dev header `X-Dev-User: <email>`, which creates the
user on first use. It is refused unless APP_ENV is local or test.
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

DEV_AUTH_ENVS = frozenset({"local", "test"})

Db = Annotated[Session, Depends(get_session)]


def _dev_email(raw: str | None) -> str:
    if settings.app_env not in DEV_AUTH_ENVS:
        raise ApiError(401, "unauthorized", "sign-in required")
    if not raw:
        raise ApiError(401, "unauthorized", "missing X-Dev-User header (local dev auth)")
    email = raw.strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email:
        raise ApiError(401, "unauthorized", "X-Dev-User must be an email address")
    return email


def current_user(db: Db, x_dev_user: Annotated[str | None, Header()] = None) -> User:
    email = _dev_email(x_dev_user)
    auth_id = f"dev:{email}"
    user = db.scalar(select(User).where(User.auth_id == auth_id))
    if user is None:
        db.execute(
            insert(User)
            .values(auth_id=auth_id, email=email, display_name=email.split("@")[0])
            .on_conflict_do_nothing(index_elements=[User.auth_id])
        )
        db.commit()
        user = db.scalar(select(User).where(User.auth_id == auth_id))
    if user is None or user.deleted_at is not None:
        raise ApiError(401, "unauthorized", "account is being deleted")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
