"""add payee contact fields (website, address, city, country, email, phone)

Revision ID: f4a1b8c2d9e7
Revises: e3f4a5b6c7d8
Create Date: 2026-03-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4a1b8c2d9e7"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payees", schema=None) as batch_op:
        batch_op.add_column(sa.Column("website", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("address", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("city", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("country", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("email", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("phone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payees", schema=None) as batch_op:
        batch_op.drop_column("phone")
        batch_op.drop_column("email")
        batch_op.drop_column("country")
        batch_op.drop_column("city")
        batch_op.drop_column("address")
        batch_op.drop_column("website")
