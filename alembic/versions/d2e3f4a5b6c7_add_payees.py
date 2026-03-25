"""add payees table and transaction.payee_id

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-03-24 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("payee_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_transactions_payee_id",
            "payees",
            ["payee_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_transactions_payee_id", type_="foreignkey")
        batch_op.drop_column("payee_id")

    op.drop_table("payees")
