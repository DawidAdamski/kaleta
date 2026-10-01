# SPDX-License-Identifier: AGPL-3.0-or-later
"""Users: e-mail, display name, and a password hash that may be absent.

A member of a hosted account (ADR-35) signs in through Supabase Auth, so their
``users`` row has no local password. Existing rows keep theirs.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-30 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("display_name", sa.String(length=100), nullable=True))
        batch_op.alter_column("password_hash", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    # Rows without a local password cannot survive a NOT NULL column, and
    # deleting them would cascade into the ledger. Refuse instead.
    bind = op.get_bind()
    orphans = bind.execute(sa.text("SELECT COUNT(*) FROM users WHERE password_hash IS NULL"))
    if orphans.scalar_one():
        msg = "Users without a local password exist (hosted members); refusing to downgrade."
        raise RuntimeError(msg)
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("password_hash", existing_type=sa.String(length=255), nullable=False)
        batch_op.drop_column("display_name")
        batch_op.drop_column("email")
