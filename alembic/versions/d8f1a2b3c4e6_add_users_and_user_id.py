"""add users table and user_id ownership columns

Revision ID: d8f1a2b3c4e6
Revises: c7e9b3f1a2d5
Create Date: 2026-07-05 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from argon2 import PasswordHasher
from sqlalchemy import text

from alembic import op

revision = "d8f1a2b3c4e6"
down_revision = "c7e9b3f1a2d5"
branch_labels = None
depends_on = None

PLACEHOLDER_USERNAME = "__placeholder__"

# Tables that receive user_id (plan scope).
USER_OWNED_TABLES: tuple[str, ...] = (
    "accounts",
    "categories",
    "transactions",
    "budgets",
    "payees",
    "planned_transactions",
    "credit_card_profiles",
    "loan_profiles",
    "assets",
    "reserve_funds",
    "tags",
    "saved_reports",
    "subscriptions",
    "counterparties",
    "personal_loans",
)

# Never populated by Alembic seed migrations — any row means a real install.
USER_DATA_TABLES: tuple[str, ...] = (
    "accounts",
    "transactions",
    "budgets",
    "payees",
    "planned_transactions",
    "credit_card_profiles",
    "loan_profiles",
    "assets",
    "reserve_funds",
    "saved_reports",
    "subscriptions",
    "counterparties",
    "personal_loans",
)

# Seeded by a4e9b2f1c6d8 (Subscriptions root + 3 children).
SEEDED_CATEGORY_COUNT = 4
# Seeded by b9d4e2c8a1f5 (8 canonical tags).
SEEDED_TAG_COUNT = 8


def _add_user_id_column(table: str) -> None:
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            f"fk_{table}_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )


def _drop_user_id_column(table: str) -> None:
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.drop_constraint(f"fk_{table}_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")


def _database_has_user_data(connection: sa.Connection) -> bool:
    """True when the DB holds user-created rows, not just Alembic seed data."""
    for table in USER_DATA_TABLES:
        count = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if count and count > 0:
            return True
    category_count = connection.execute(text("SELECT COUNT(*) FROM categories")).scalar()
    if category_count and category_count > SEEDED_CATEGORY_COUNT:
        return True
    tag_count = connection.execute(text("SELECT COUNT(*) FROM tags")).scalar()
    return bool(tag_count and tag_count > SEEDED_TAG_COUNT)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    for table in USER_OWNED_TABLES:
        _add_user_id_column(table)

    connection = op.get_bind()
    if _database_has_user_data(connection):
        placeholder_hash = PasswordHasher().hash("PLACEHOLDER-NOT-LOGINABLE")
        connection.execute(
            text(
                "INSERT INTO users (username, password_hash, created_at) "
                "VALUES (:username, :password_hash, CURRENT_TIMESTAMP)"
            ),
            {"username": PLACEHOLDER_USERNAME, "password_hash": placeholder_hash},
        )
        user_id = connection.execute(
            text("SELECT id FROM users WHERE username = :username"),
            {"username": PLACEHOLDER_USERNAME},
        ).scalar_one()
        for table in USER_OWNED_TABLES:
            connection.execute(
                text(f"UPDATE {table} SET user_id = :user_id WHERE user_id IS NULL"),
                {"user_id": user_id},
            )


def downgrade() -> None:
    for table in reversed(USER_OWNED_TABLES):
        _drop_user_id_column(table)
    op.drop_table("users")
