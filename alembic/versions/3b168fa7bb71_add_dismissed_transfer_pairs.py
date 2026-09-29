# SPDX-License-Identifier: AGPL-3.0-or-later
"""Record transfer pairs the user has dismissed.

Revision ID: 3b168fa7bb71
Revises: q1r2s3t4u5v6
Create Date: 2026-09-29 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3b168fa7bb71"
down_revision: str | Sequence[str] | None = "q1r2s3t4u5v6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A new table, so no batch mode is needed; the unique constraint is
    # declared inline, which SQLite accepts at CREATE TABLE time.
    op.create_table(
        "dismissed_transfer_pairs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_transaction_id", sa.Integer(), nullable=False),
        sa.Column("second_transaction_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["first_transaction_id"],
            ["transactions.id"],
            name="fk_dismissed_transfer_pairs_first_transaction_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["second_transaction_id"],
            ["transactions.id"],
            name="fk_dismissed_transfer_pairs_second_transaction_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "first_transaction_id",
            "second_transaction_id",
            name="uq_dismissed_transfer_pair",
        ),
    )


def downgrade() -> None:
    op.drop_table("dismissed_transfer_pairs")
