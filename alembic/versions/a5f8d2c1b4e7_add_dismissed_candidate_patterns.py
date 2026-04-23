"""add dismissed_candidate_patterns table

Revision ID: a5f8d2c1b4e7
Revises: e7c4b1a3d9f2
Create Date: 2026-04-23 14:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a5f8d2c1b4e7"
down_revision = "e7c4b1a3d9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dismissed_candidate_patterns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payee_id", sa.Integer(), nullable=True),
        sa.Column("merchant_key", sa.String(length=60), nullable=True),
        sa.Column("amount_bucket", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["payee_id"],
            ["payees.id"],
            name="fk_dismissed_candidate_patterns_payee_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "payee_id",
            "merchant_key",
            "amount_bucket",
            name="uq_dismissed_candidate_pattern",
        ),
    )


def downgrade() -> None:
    op.drop_table("dismissed_candidate_patterns")
