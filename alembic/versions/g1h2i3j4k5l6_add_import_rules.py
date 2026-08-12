"""add import_rules table

Revision ID: g1h2i3j4k5l6
Revises: f3c5d7e9a1b2
Create Date: 2026-08-11 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "g1h2i3j4k5l6"
down_revision = "f3c5d7e9a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename_pattern", sa.String(length=200), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("column_mapping", sa.JSON(), nullable=False),
        sa.Column("encoding", sa.String(length=40), nullable=True),
        sa.Column("delimiter", sa.String(length=8), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
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
            ["account_id"],
            ["accounts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_import_rules_filename_pattern",
        "import_rules",
        ["filename_pattern"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_rules_filename_pattern", table_name="import_rules")
    op.drop_table("import_rules")
