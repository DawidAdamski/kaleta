# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drop ``local_key_material``: a family's sealed key lives on its member row.

ADR-38 (postgres-only B2b). The single-family layout kept its owner's sealed
data key in this table of the family's own schema; every family now keeps it
on ``public.tenant_members`` (``TenantKeyStore``), and nothing reads the table
any more. A family schema never wrote it, so it is empty wherever this runs.

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
Create Date: 2026-10-10 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "s3t4u5v6w7x8"
down_revision = "r2s3t4u5v6w7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("local_key_material")


def downgrade() -> None:
    op.create_table(
        "local_key_material",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("private_key_wrapped", sa.LargeBinary(), nullable=False),
        sa.Column("private_key_salt", sa.LargeBinary(), nullable=False),
        sa.Column("kdf_params", sa.Text(), nullable=False),
        sa.Column("recovery_wrapped", sa.LargeBinary(), nullable=True),
        sa.Column("recovery_salt", sa.LargeBinary(), nullable=True),
        sa.Column("dek_sealed", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
