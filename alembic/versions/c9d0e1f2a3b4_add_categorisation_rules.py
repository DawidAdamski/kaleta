"""add categorisation_rules table

Revision ID: c9d0e1f2a3b4
Revises: e9f2a3b4c5d6
Create Date: 2026-07-26 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "e9f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categorisation_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pattern", sa.String(length=200), nullable=False),
        sa.Column(
            "match_mode",
            sa.Enum("contains", name="rulematchmode", native_enum=False),
            nullable=False,
            server_default="contains",
        ),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_categorisation_rules_pattern",
        "categorisation_rules",
        ["pattern"],
    )


def downgrade() -> None:
    op.drop_index("ix_categorisation_rules_pattern", table_name="categorisation_rules")
    op.drop_table("categorisation_rules")
