"""add subscriptions table

Revision ID: e7c4b1a3d9f2
Revises: f2a8c4d1e5b7
Create Date: 2026-04-23 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e7c4b1a3d9f2"
down_revision = "f2a8c4d1e5b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payee_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("cadence_days", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.Date(), nullable=True),
        sa.Column("next_expected_at", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "muted",
                "cancelled",
                name="subscriptionstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("muted_until", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.Date(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column(
            "auto_renew",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
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
        sa.ForeignKeyConstraint(
            ["payee_id"],
            ["payees.id"],
            name="fk_subscriptions_payee_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_subscriptions_category_id",
            ondelete="SET NULL",
        ),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
