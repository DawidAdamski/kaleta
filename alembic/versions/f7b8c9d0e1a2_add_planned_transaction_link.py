# SPDX-License-Identifier: AGPL-3.0-or-later
"""Link transactions to posted planned occurrences.

Revision ID: f7b8c9d0e1a2
Revises: e9f2a3b4c5d6
Create Date: 2026-07-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f7b8c9d0e1a2"
down_revision: str | Sequence[str] | None = "e9f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("planned_transaction_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_transactions_planned_transaction_id",
            ["planned_transaction_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_transactions_planned_transaction_id",
            "planned_transactions",
            ["planned_transaction_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_transactions_planned_occurrence",
            ["planned_transaction_id", "date"],
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_constraint("uq_transactions_planned_occurrence", type_="unique")
        batch_op.drop_constraint("fk_transactions_planned_transaction_id", type_="foreignkey")
        batch_op.drop_index("ix_transactions_planned_transaction_id")
        batch_op.drop_column("planned_transaction_id")
