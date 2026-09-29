# SPDX-License-Identifier: AGPL-3.0-or-later
"""Link a planned transaction to the payee it pays.

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-09-29 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "q1r2s3t4u5v6"
down_revision: str | Sequence[str] | None = "p0q1r2s3t4u5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable with no backfill: existing plans were entered by hand and name
    # no payee; they keep matching payments by name as before.
    with op.batch_alter_table("planned_transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("payee_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_planned_transactions_payee_id"), ["payee_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_planned_transactions_payee_id",
            "payees",
            ["payee_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("planned_transactions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_planned_transactions_payee_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_planned_transactions_payee_id"))
        batch_op.drop_column("payee_id")
