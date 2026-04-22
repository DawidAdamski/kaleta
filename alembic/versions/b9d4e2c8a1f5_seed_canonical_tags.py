"""seed 8 canonical tags

Revision ID: b9d4e2c8a1f5
Revises: a9b8c7d6e5f4
Create Date: 2026-04-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "b9d4e2c8a1f5"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None


# English name is canonical; users can rename freely.
# Icon names come from Material Icons.
SEED_TAGS: list[tuple[str, str]] = [
    ("Transfer", "swap_horiz"),
    ("Card", "credit_card"),
    ("Cash", "payments"),
    ("Online", "language"),
    ("Subscription", "autorenew"),
    ("Refundable", "assignment_return"),
    ("Business", "work"),
    ("Recurring", "event_repeat"),
]


def upgrade() -> None:
    for name, icon in SEED_TAGS:
        op.execute(
            "INSERT INTO tags (name, icon, created_at, updated_at) "
            f"SELECT '{name}', '{icon}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            f"WHERE NOT EXISTS (SELECT 1 FROM tags WHERE LOWER(name) = LOWER('{name}'))"
        )


def downgrade() -> None:
    names = ", ".join(f"'{name}'" for name, _ in SEED_TAGS)
    op.execute(f"DELETE FROM tags WHERE name IN ({names})")
