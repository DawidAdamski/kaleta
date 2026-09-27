# SPDX-License-Identifier: AGPL-3.0-or-later
"""Link a personal loan to the transaction that moved its principal.

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-09-27 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "p0q1r2s3t4u5"
down_revision: str | Sequence[str] | None = "o9p0q1r2s3t4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable with no backfill: existing loans were recorded without a ledger
    # link, and NULL keeps them exactly as they were.
    with op.batch_alter_table("personal_loans", schema=None) as batch_op:
        batch_op.add_column(sa.Column("transaction_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_personal_loans_transaction_id",
            "transactions",
            ["transaction_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint("uq_personal_loans_transaction_id", ["transaction_id"])


def downgrade() -> None:
    with op.batch_alter_table("personal_loans", schema=None) as batch_op:
        batch_op.drop_constraint("uq_personal_loans_transaction_id", type_="unique")
        batch_op.drop_constraint("fk_personal_loans_transaction_id", type_="foreignkey")
        batch_op.drop_column("transaction_id")
