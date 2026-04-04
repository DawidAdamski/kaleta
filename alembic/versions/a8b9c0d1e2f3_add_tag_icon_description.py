"""add icon and description columns to tags

Revision ID: a8b9c0d1e2f3
Revises: f6a7b8c9d0e1
Create Date: 2026-03-09 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tags", sa.Column("icon", sa.String(50), nullable=True))
    op.add_column("tags", sa.Column("description", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("tags", "description")
    op.drop_column("tags", "icon")
