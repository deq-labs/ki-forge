"""Seed exercises added to db/seed/program.json after 0002 (technique progression steps, #58).

Inserts every seed exercise whose slug is not in the table yet, then links their garage swaps. Running it
against a database seeded from the current program.json is a no-op, so it is safe on any database.

Revision ID: 0004
Revises: 0003
"""

import json

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    conn = op.get_bind()
    have = {slug for (slug,) in conn.execute(sa.text("SELECT slug FROM exercises"))}
    added = []
    for e in seed["exercises"]:
        if e["slug"] in have:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO exercises (slug, name, equipment, needs_garage_space, increment_lb, is_timed) "
                "VALUES (:slug, :name, :equipment, :ngs, :inc, :timed)"
            ),
            {
                "slug": e["slug"],
                "name": e["name"],
                "equipment": e["equipment"],
                "ngs": e["needs_garage_space"],
                "inc": e["increment_lb"],
                "timed": e["is_timed"],
            },
        )
        added.append(e)
    for e in added:
        if e["swap"]:
            conn.execute(
                sa.text(
                    "UPDATE exercises SET swap_exercise_id = (SELECT id FROM exercises WHERE slug = :swap) "
                    "WHERE slug = :slug"
                ),
                {"swap": e["swap"], "slug": e["slug"]},
            )


def downgrade() -> None:
    # Exercises may be referenced by logged sets; leave them in place.
    pass
