"""add transactions.irregular_item_id

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-10-12 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "v6w7x8y9z0a1"
down_revision = "u5v6w7x8y9z0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, no backfill: nothing was paid against an item before items existed.
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("irregular_item_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "transactions_irregular_item_id_fkey",
            "irregular_items",
            ["irregular_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_transactions_irregular_item_id", ["irregular_item_id"])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("ix_transactions_irregular_item_id")
        batch_op.drop_constraint("transactions_irregular_item_id_fkey", type_="foreignkey")
        batch_op.drop_column("irregular_item_id")
