"""align enum columns and saved_reports timestamps

Revision ID: a9b8c7d6e5f4
Revises: f4a1b8c2d9e7
Create Date: 2026-04-04 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a9b8c7d6e5f4"
down_revision = "f4a1b8c2d9e7"
branch_labels = None
depends_on = None


ASSET_TYPE = sa.Enum(
    "REAL_ESTATE",
    "VEHICLE",
    "VALUABLES",
    "OTHER",
    name="assettype",
    native_enum=False,
)
TRANSACTION_TYPE = sa.Enum(
    "INCOME",
    "EXPENSE",
    "TRANSFER",
    name="transactiontype",
    native_enum=False,
)
RECURRENCE_FREQUENCY = sa.Enum(
    "ONCE",
    "DAILY",
    "WEEKLY",
    "BIWEEKLY",
    "MONTHLY",
    "QUARTERLY",
    "YEARLY",
    name="recurrencefrequency",
    native_enum=False,
)


def upgrade() -> None:
    op.execute("UPDATE assets SET type = UPPER(type)")
    op.execute("UPDATE planned_transactions SET type = UPPER(type), frequency = UPPER(frequency)")
    op.execute(
        """
        UPDATE saved_reports
        SET
            created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
            updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
        """
    )

    with op.batch_alter_table("assets") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=sa.String(length=50),
            type_=ASSET_TYPE,
            existing_nullable=False,
        )

    with op.batch_alter_table("planned_transactions") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=sa.String(length=20),
            type_=TRANSACTION_TYPE,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "frequency",
            existing_type=sa.String(length=20),
            type_=RECURRENCE_FREQUENCY,
            existing_nullable=False,
        )

    with op.batch_alter_table("saved_reports") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )


def downgrade() -> None:
    with op.batch_alter_table("saved_reports") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=True,
            server_default=None,
        )
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            nullable=True,
            server_default=None,
        )

    with op.batch_alter_table("planned_transactions") as batch_op:
        batch_op.alter_column(
            "frequency",
            existing_type=RECURRENCE_FREQUENCY,
            type_=sa.String(length=20),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "type",
            existing_type=TRANSACTION_TYPE,
            type_=sa.String(length=20),
            existing_nullable=False,
        )

    with op.batch_alter_table("assets") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=ASSET_TYPE,
            type_=sa.String(length=50),
            existing_nullable=False,
        )

    op.execute("UPDATE assets SET type = LOWER(type)")
    op.execute("UPDATE planned_transactions SET type = LOWER(type), frequency = LOWER(frequency)")
