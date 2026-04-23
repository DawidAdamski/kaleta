"""add is_subscriptions_root to categories + seed Subscriptions tree

Revision ID: a4e9b2f1c6d8
Revises: d5b8a2e7c1f4
Create Date: 2026-04-23 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a4e9b2f1c6d8"
down_revision = "d5b8a2e7c1f4"
branch_labels = None
depends_on = None


SUBSCRIPTIONS_ROOT_NAME = "Subscriptions"
SUBSCRIPTIONS_CHILDREN = ("Monthly", "Yearly", "Other")


def upgrade() -> None:
    # 1) Add the column via batch (SQLite-safe).
    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_subscriptions_root",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # 2) Idempotent seed: only run if no root with is_subscriptions_root=1 exists.
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM categories WHERE is_subscriptions_root = 1 LIMIT 1")
    ).fetchone()
    if existing is not None:
        return

    # Insert the root. Use parameter binding for safety.
    result = conn.execute(
        sa.text(
            "INSERT INTO categories "
            "(name, type, parent_id, is_subscriptions_root, created_at, updated_at) "
            "VALUES (:name, :type, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"name": SUBSCRIPTIONS_ROOT_NAME, "type": "EXPENSE"},
    )
    root_id = result.lastrowid
    if root_id is None:
        # Fallback for drivers that don't expose lastrowid.
        root_row = conn.execute(
            sa.text(
                "SELECT id FROM categories "
                "WHERE is_subscriptions_root = 1 ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()
        if root_row is None:
            return
        root_id = root_row[0]

    for child_name in SUBSCRIPTIONS_CHILDREN:
        conn.execute(
            sa.text(
                "INSERT INTO categories "
                "(name, type, parent_id, is_subscriptions_root, created_at, updated_at) "
                "VALUES (:name, :type, :parent_id, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"name": child_name, "type": "EXPENSE", "parent_id": root_id},
        )


def downgrade() -> None:
    # We intentionally keep the seeded categories — they're valid rows and may
    # already have user transactions attached. Only drop the flag column.
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_column("is_subscriptions_root")
