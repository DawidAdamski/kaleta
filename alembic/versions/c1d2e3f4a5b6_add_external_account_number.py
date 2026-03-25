"""add external_account_number to accounts

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-03-24 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("external_account_number", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accounts", "external_account_number")
