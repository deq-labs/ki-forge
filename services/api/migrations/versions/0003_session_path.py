"""Store the path each session was done on, so changing path only affects sessions not yet started.

Nullable: sessions logged before this migration are backfilled from their run's path; a null still means
"use the run's path".

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workout_sessions",
        sa.Column("path_id", sa.SmallInteger(), sa.ForeignKey("paths.id"), nullable=True),
    )
    op.execute(
        "UPDATE workout_sessions ws SET path_id = e.path_id FROM enrollments e WHERE e.id = ws.enrollment_id"
    )


def downgrade() -> None:
    op.drop_column("workout_sessions", "path_id")
