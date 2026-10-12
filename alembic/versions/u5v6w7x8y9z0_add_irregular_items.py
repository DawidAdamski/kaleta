"""add irregular_items

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-10-12 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "u5v6w7x8y9z0"
down_revision = "t4u5v6w7x8y9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "irregular_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "fund_id",
            sa.Integer(),
            sa.ForeignKey("reserve_funds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # ``EncryptedText``: ciphertext, like the fund's own name.
        sa.Column("name", sa.LargeBinary(), nullable=False),
        sa.Column("yearly_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("due_month", sa.Integer(), nullable=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_irregular_items_fund_id", "irregular_items", ["fund_id"])


def downgrade() -> None:
    op.drop_index("ix_irregular_items_fund_id", table_name="irregular_items")
    op.drop_table("irregular_items")
