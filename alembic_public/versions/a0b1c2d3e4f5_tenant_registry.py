# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tenant registry: tenants, tenant_members, tenant_invites.

Revision ID: a0b1c2d3e4f5
Revises:
Create Date: 2026-09-30 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"


def _status(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=20)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schema_name", sa.String(length=63), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _status("tenant_status", "provisioning", "active", "suspended", "rekeying", "deleting"),
            nullable=False,
        ),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "tenant_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey(f"{SCHEMA}.tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("auth_subject", sa.String(length=255), nullable=False, unique=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("role", _status("tenant_role", "owner", "member"), nullable=False),
        sa.Column(
            "status",
            _status("tenant_member_status", "pending", "active", "removed"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=True),
        sa.Column("private_key_wrapped", sa.LargeBinary(), nullable=True),
        sa.Column("private_key_salt", sa.LargeBinary(), nullable=True),
        sa.Column("kdf_params", sa.Text(), nullable=True),
        sa.Column("recovery_wrapped", sa.LargeBinary(), nullable=True),
        sa.Column("recovery_salt", sa.LargeBinary(), nullable=True),
        sa.Column("dek_sealed", sa.LargeBinary(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_tenant_members_tenant_id", "tenant_members", ["tenant_id"], schema=SCHEMA)
    op.create_table(
        "tenant_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey(f"{SCHEMA}.tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", _status("tenant_role", "owner", "member"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_tenant_invites_tenant_id", "tenant_invites", ["tenant_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_tenant_invites_tenant_id", table_name="tenant_invites", schema=SCHEMA)
    op.drop_table("tenant_invites", schema=SCHEMA)
    op.drop_index("ix_tenant_members_tenant_id", table_name="tenant_members", schema=SCHEMA)
    op.drop_table("tenant_members", schema=SCHEMA)
    op.drop_table("tenants", schema=SCHEMA)
