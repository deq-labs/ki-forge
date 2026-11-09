"""A session done as the program's short day (#81).

The short version drops the roles in the program's `short_day.skip_roles` (Iron Tempo: finisher, core,
X3), and the rules engine scores the session against it, so a finished short day clears.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workout_sessions",
        sa.Column("short_day", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("workout_sessions", "short_day")
