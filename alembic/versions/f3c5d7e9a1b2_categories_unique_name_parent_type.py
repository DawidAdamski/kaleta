# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scope category uniqueness to (name, parent_id, type).

Revision ID: f3c5d7e9a1b2
Revises: c9d0e1f2a3b4
Create Date: 2026-08-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f3c5d7e9a1b2"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_constraint("uq_categories_name_parent", type_="unique")
        batch_op.create_unique_constraint(
            "uq_categories_name_parent_type",
            ["name", "parent_id", "type"],
        )


def downgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_constraint("uq_categories_name_parent_type", type_="unique")
        batch_op.create_unique_constraint(
            "uq_categories_name_parent",
            ["name", "parent_id"],
        )
