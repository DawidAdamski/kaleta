"""add transactions.notes column

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-09-03 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "j4k5l6m7n8o9"
down_revision = "i3j4k5l6m7n8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "notes")
