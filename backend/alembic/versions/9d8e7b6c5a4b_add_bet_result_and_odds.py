"""add bet result and odds fields

Revision ID: 9d8e7b6c5a4b
Revises: 3f3a0e2f5c2b
Create Date: 2026-01-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "9d8e7b6c5a4b"
down_revision = "3f3a0e2f5c2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bets") as batch_op:
        batch_op.add_column(sa.Column("odds_decimal", sa.Numeric(12, 4), nullable=True))
        batch_op.add_column(
            sa.Column(
                "result",
                sa.String(length=10),
                nullable=False,
                server_default="pending",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("bets") as batch_op:
        batch_op.drop_column("result")
        batch_op.drop_column("odds_decimal")
