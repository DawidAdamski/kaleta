"""add notes column to subscriptions

Revision ID: b6d9c5a2f8e3
Revises: a5f8d2c1b4e7
Create Date: 2026-04-23 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b6d9c5a2f8e3"
down_revision = "a5f8d2c1b4e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.drop_column("notes")
