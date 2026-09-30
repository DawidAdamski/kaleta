# SPDX-License-Identifier: AGPL-3.0-or-later
"""A savings goal's target date.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-30 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("reserve_funds", schema=None) as batch_op:
        batch_op.add_column(sa.Column("target_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reserve_funds", schema=None) as batch_op:
        batch_op.drop_column("target_date")
