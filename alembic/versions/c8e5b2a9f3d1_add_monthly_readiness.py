"""add monthly_readiness table

Revision ID: c8e5b2a9f3d1
Revises: a4f9d2e7c1b8
Create Date: 2026-04-22 04:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c8e5b2a9f3d1"
down_revision = "a4f9d2e7c1b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_readiness",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column(
            "stage_1_done",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "stage_2_done",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "stage_3_done",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "stage_4_done",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "seen_planned_ids",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("year", "month", name="uq_monthly_readiness_year_month"),
    )


def downgrade() -> None:
    op.drop_table("monthly_readiness")
