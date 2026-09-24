"""add reserve_funds.target_from_spending

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-09-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "n8o9p0q1r2s3"
down_revision = "m7n8o9p0q1r2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reserve_funds") as batch_op:
        batch_op.add_column(
            sa.Column(
                "target_from_spending",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("reserve_funds") as batch_op:
        batch_op.drop_column("target_from_spending")
