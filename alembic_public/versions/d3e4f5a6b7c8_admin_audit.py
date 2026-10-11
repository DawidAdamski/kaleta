# SPDX-License-Identifier: AGPL-3.0-or-later
"""The instance administrator's audit trail (instance-admin-panel).

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-10-11 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | Sequence[str] | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"


def upgrade() -> None:
    op.create_table(
        "admin_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("identity_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_admin_audit_tenant_id", "admin_audit", ["tenant_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_admin_audit_tenant_id", table_name="admin_audit", schema=SCHEMA)
    op.drop_table("admin_audit", schema=SCHEMA)
