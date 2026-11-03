"""The `delete_user` job: remove a user and every row they own (ON DELETE CASCADE does the rest).

Photo objects in R2 are removed here too once scans upload photos (M5).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.jobs import handler
from app.models import User


@handler("delete_user")
def delete_user(db: Session, payload: dict[str, Any]) -> None:
    db.execute(delete(User).where(User.id == uuid.UUID(payload["user_id"]), User.deleted_at.is_not(None)))
