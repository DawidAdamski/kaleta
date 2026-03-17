"""add planned_transactions table

Revision ID: b0c1d2e3f4a5
Revises: a8b9c0d1e2f3
Create Date: 2026-03-09 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b0c1d2e3f4a5"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planned_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
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
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_planned_transactions_account_id", "planned_transactions", ["account_id"]
    )
    op.create_index(
        "ix_planned_transactions_start_date", "planned_transactions", ["start_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_planned_transactions_start_date", "planned_transactions")
    op.drop_index("ix_planned_transactions_account_id", "planned_transactions")
    op.drop_table("planned_transactions")
