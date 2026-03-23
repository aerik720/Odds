"""add alias tables

Revision ID: 1d1fb6d5c0c4
Revises: 69954a2a6ca5
Create Date: 2026-01-21 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "1d1fb6d5c0c4"
down_revision = "69954a2a6ca5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_aliases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("bookmaker_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("external_event_id", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["bookmaker_id"], ["bookmakers.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.UniqueConstraint("bookmaker_id", "external_event_id"),
    )

    op.create_table(
        "market_aliases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("bookmaker_id", sa.String(length=36), nullable=False),
        sa.Column("market_id", sa.String(length=36), nullable=False),
        sa.Column("external_market_id", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["bookmaker_id"], ["bookmakers.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.UniqueConstraint("bookmaker_id", "external_market_id"),
    )


def downgrade() -> None:
    op.drop_table("market_aliases")
    op.drop_table("event_aliases")
