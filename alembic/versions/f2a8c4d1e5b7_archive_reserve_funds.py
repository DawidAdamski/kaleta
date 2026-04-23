"""archive columns for reserve_funds

Revision ID: f2a8c4d1e5b7
Revises: c8e5b2a9f3d1
Create Date: 2026-04-23 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f2a8c4d1e5b7"
down_revision = "c8e5b2a9f3d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reserve_funds") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_archived",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reserve_funds") as batch_op:
        batch_op.drop_column("archived_at")
        batch_op.drop_column("is_archived")
