"""The resistance band a set was done with (X3 sets on Iron Tempo), #67.

Free text from the user's band list (e.g. "Dark gray"); null for every other set.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("set_logs", sa.Column("band", sa.Text(), nullable=True))
    op.create_check_constraint("set_logs_band_len", "set_logs", "char_length(band) <= 32")


def downgrade() -> None:
    op.drop_column("set_logs", "band")
