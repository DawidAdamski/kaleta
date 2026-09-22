"""add bug_reports table

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-09-22 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "l6m7n8o9p0q1"
down_revision = "k5l6m7n8o9p0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bug_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("summary", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("event_ids", sa.JSON(), nullable=False),
        sa.Column("route", sa.String(length=260), nullable=True),
        sa.Column("app_version", sa.String(length=40), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("viewport", sa.String(length=40), nullable=True),
        sa.Column("locale", sa.String(length=20), nullable=True),
        sa.Column("log_excerpt", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("NEW", "SEEN", "CLOSED", name="bugreportstatus", native_enum=False),
            nullable=False,
            server_default="NEW",
        ),
        sa.Column("external_ref", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(op.f("ix_bug_reports_report_id"), "bug_reports", ["report_id"], unique=True)
    op.create_index(op.f("ix_bug_reports_created_at"), "bug_reports", ["created_at"])
    op.create_index(op.f("ix_bug_reports_session_id"), "bug_reports", ["session_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bug_reports_session_id"), table_name="bug_reports")
    op.drop_index(op.f("ix_bug_reports_created_at"), table_name="bug_reports")
    op.drop_index(op.f("ix_bug_reports_report_id"), table_name="bug_reports")
    op.drop_table("bug_reports")
