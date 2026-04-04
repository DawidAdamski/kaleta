"""add currency to accounts and exchange_rate to transactions

Revision ID: a1b2c3d4e5f6
Revises: d7a3e1f2b8c5
Create Date: 2026-03-08 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "d7a3e1f2b8c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="PLN")
        )

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "exchange_rate",
                sa.Numeric(precision=15, scale=6),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_column("exchange_rate")

    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.drop_column("currency")
