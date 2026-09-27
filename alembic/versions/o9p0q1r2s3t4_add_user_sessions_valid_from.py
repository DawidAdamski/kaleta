"""add users.sessions_valid_from

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-09-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "o9p0q1r2s3t4"
down_revision = "n8o9p0q1r2s3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable with no backfill: NULL reads as "never revoked", which is what
    # every existing account is.
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("sessions_valid_from", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("sessions_valid_from")
