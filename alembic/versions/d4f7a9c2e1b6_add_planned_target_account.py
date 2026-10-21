"""add planned_transactions.target_account_id

Revision ID: d4f7a9c2e1b6
Revises: e9ecbe7dd5b0
Create Date: 2026-10-21 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d4f7a9c2e1b6"
down_revision = "e9ecbe7dd5b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The destination account of a structured self-transfer (the "pay yourself
    # a salary" plan). Nullable, no backfill: existing plans are single-leg and
    # keep ``NULL`` (they post one leg as before). ``SET NULL`` so deleting the
    # target account does not cascade-delete the whole plan.
    op.add_column(
        "planned_transactions",
        sa.Column("target_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "planned_transactions_target_account_id_fkey",
        "planned_transactions",
        "accounts",
        ["target_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "planned_transactions_target_account_id_fkey",
        "planned_transactions",
        type_="foreignkey",
    )
    op.drop_column("planned_transactions", "target_account_id")
