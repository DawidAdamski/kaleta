"""add yearly_plans table

Revision ID: e6b2c1a9f083
Revises: c5a8d1e3b4f7
Create Date: 2026-04-22 02:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e6b2c1a9f083"
down_revision = "c5a8d1e3b4f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "yearly_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("income_lines", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("fixed_lines", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("variable_lines", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("reserves_lines", sa.Text(), nullable=False, server_default="[]"),
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
        sa.UniqueConstraint("year", name="uq_yearly_plans_year"),
    )


def downgrade() -> None:
    op.drop_table("yearly_plans")
