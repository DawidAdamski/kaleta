# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local logins on the registry: local_identities, instance_settings (ADR-38).

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-10-10 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"


def upgrade() -> None:
    op.create_table(
        "local_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_instance_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "instance_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("instance_settings", schema=SCHEMA)
    op.drop_table("local_identities", schema=SCHEMA)
