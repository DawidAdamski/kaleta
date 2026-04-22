"""add reserve_funds table

Revision ID: a4f9d2e7c1b8
Revises: e6b2c1a9f083
Create Date: 2026-04-22 03:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a4f9d2e7c1b8"
down_revision = "e6b2c1a9f083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reserve_funds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "emergency",
                "irregular",
                "vacation",
                name="reservefundkind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "target_amount",
            sa.Numeric(precision=15, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "backing_mode",
            sa.Enum(
                "account",
                "envelope",
                name="reservefundbackingmode",
                native_enum=False,
            ),
            nullable=False,
            server_default="account",
        ),
        sa.Column(
            "backing_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "backing_category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("emergency_multiplier", sa.Integer(), nullable=True),
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
    )


def downgrade() -> None:
    op.drop_table("reserve_funds")
