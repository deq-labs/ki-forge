"""The row a set was logged on (`slot` = the session row's key, e.g. "p1"), #66.

Needed when the same exercise is in two rows of a session (Iron Tempo Monday: deadlifts in the EMOM and
in the finisher). Null for sets logged before this and for plain rows: they are matched by exercise.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("set_logs", sa.Column("slot", sa.Text(), nullable=True))
    op.create_check_constraint("set_logs_slot_len", "set_logs", "char_length(slot) <= 16")


def downgrade() -> None:
    op.drop_column("set_logs", "slot")
