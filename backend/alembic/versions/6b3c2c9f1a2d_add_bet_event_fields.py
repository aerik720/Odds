"""add bet event fields

Revision ID: 6b3c2c9f1a2d
Revises: 9d8e7b6c5a4b
Create Date: 2026-03-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "6b3c2c9f1a2d"
down_revision = "9d8e7b6c5a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bets") as batch_op:
        batch_op.add_column(sa.Column("event_id", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("event_start_time", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bets") as batch_op:
        batch_op.drop_column("event_start_time")
        batch_op.drop_column("event_id")
