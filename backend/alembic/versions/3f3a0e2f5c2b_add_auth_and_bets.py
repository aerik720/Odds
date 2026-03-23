"""add auth fields and bets table

Revision ID: 3f3a0e2f5c2b
Revises: 1d1fb6d5c0c4
Create Date: 2026-01-23 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "3f3a0e2f5c2b"
down_revision = "1d1fb6d5c0c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("password_hash", sa.String(length=200), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )

    op.create_table(
        "bets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("external_key", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("event", sa.String(length=200), nullable=False),
        sa.Column("market", sa.String(length=200), nullable=False),
        sa.Column("outcome", sa.String(length=100), nullable=False),
        sa.Column("stake", sa.Numeric(12, 2), nullable=False),
        sa.Column("payout", sa.Numeric(12, 2), nullable=False),
        sa.Column("profit", sa.Numeric(12, 2), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id", "external_key"),
    )


def downgrade() -> None:
    op.drop_table("bets")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_active")
        batch_op.drop_column("password_hash")
