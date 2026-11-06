"""1RMs the user enters for % of 1RM targets (Iron Tempo, #65).

One row per user and lift, in lb (CLAUDE.md rule 4). `updated_at` tells when it was last tested, so the
app can ask for a re-test after a deload week.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_lifts",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("exercise_id", sa.SmallInteger(), sa.ForeignKey("exercises.id"), primary_key=True),
        sa.Column("one_rm_lb", sa.Numeric(6, 2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("one_rm_lb > 0 AND one_rm_lb < 2000", name="user_lifts_one_rm_range"),
    )


def downgrade() -> None:
    op.drop_table("user_lifts")
