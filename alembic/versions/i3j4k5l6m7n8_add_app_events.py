"""add app_events table

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-08-26 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "i3j4k5l6m7n8"
down_revision = "h2i3j4k5l6m7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("route", sa.String(length=260), nullable=True),
        sa.Column("exception_class", sa.String(length=200), nullable=False),
        sa.Column("stack_hash", sa.String(length=64), nullable=False),
        sa.Column("stack_trace", sa.Text(), nullable=False),
        sa.Column("app_version", sa.String(length=40), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(op.f("ix_app_events_event_id"), "app_events", ["event_id"], unique=True)
    op.create_index(op.f("ix_app_events_occurred_at"), "app_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_app_events_occurred_at"), table_name="app_events")
    op.drop_index(op.f("ix_app_events_event_id"), table_name="app_events")
    op.drop_table("app_events")
