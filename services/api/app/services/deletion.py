"""The `delete_user` job: remove a user and every row they own (ON DELETE CASCADE does the rest).

The Clerk account goes first, so a failure there retries the job with the row still marked deleted.
Photo objects in R2 are removed here too once scans upload photos (M5).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.jobs import handler
from app.models import User
from app.services import auth


@handler("delete_user")
def delete_user(db: Session, payload: dict[str, Any]) -> None:
    user_id = uuid.UUID(payload["user_id"])
    auth_id = db.scalar(select(User.auth_id).where(User.id == user_id, User.deleted_at.is_not(None)))
    if auth_id is None:
        return
    if not auth_id.startswith("dev:") and settings.clerk_secret_key:
        auth.delete_clerk_user(auth_id)
    db.execute(delete(User).where(User.id == user_id, User.deleted_at.is_not(None)))
