"""add transactions.gift_id

Revision ID: e9ecbe7dd5b0
Revises: c9c34c5fcfe3
Create Date: 2026-10-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e9ecbe7dd5b0"
down_revision = "c9c34c5fcfe3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, no backfill: expenses recorded before gifts existed paid for
    # no gift. A gift is "bought" once a transaction points at it (``KAL-GFT-003``).
    op.add_column("transactions", sa.Column("gift_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "transactions_gift_id_fkey",
        "transactions",
        "gifts",
        ["gift_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_gift_id", "transactions", ["gift_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_gift_id", table_name="transactions")
    op.drop_constraint("transactions_gift_id_fkey", "transactions", type_="foreignkey")
    op.drop_column("transactions", "gift_id")
