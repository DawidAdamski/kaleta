"""add logo_path to institutions

Revision ID: c5a8d1e3b4f7
Revises: b9d4e2c8a1f5
Create Date: 2026-04-22 01:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c5a8d1e3b4f7"
down_revision = "b9d4e2c8a1f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("institutions", sa.Column("logo_path", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("institutions", "logo_path")
