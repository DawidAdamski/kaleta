"""add gifts

Revision ID: c9c34c5fcfe3
Revises: v6w7x8y9z0a1
Create Date: 2026-10-16 11:39:25.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c9c34c5fcfe3"
down_revision = "v6w7x8y9z0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        # ``EncryptedText``: ciphertext, like other user text.
        sa.Column("person", sa.LargeBinary(), nullable=False),
        sa.Column("occasion", sa.LargeBinary(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
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
    op.create_index("ix_gifts_user_id", "gifts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_gifts_user_id", table_name="gifts")
    op.drop_table("gifts")
