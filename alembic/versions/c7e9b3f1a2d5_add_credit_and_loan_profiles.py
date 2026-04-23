"""add credit card and loan profile tables

Revision ID: c7e9b3f1a2d5
Revises: a4e9b2f1c6d8
Create Date: 2026-04-23 17:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c7e9b3f1a2d5"
down_revision = "a4e9b2f1c6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_card_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("credit_limit", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column(
            "statement_day",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "payment_due_day",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("25"),
        ),
        sa.Column(
            "min_payment_pct",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default=sa.text("0.02"),
        ),
        sa.Column(
            "min_payment_floor",
            sa.Numeric(precision=15, scale=2),
            nullable=False,
            server_default=sa.text("30.00"),
        ),
        sa.Column(
            "apr",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_credit_card_profiles_account_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("account_id", name="uq_credit_card_account"),
    )

    op.create_table(
        "loan_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("principal", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("apr", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("monthly_payment", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_loan_profiles_account_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("account_id", name="uq_loan_account"),
    )


def downgrade() -> None:
    op.drop_table("loan_profiles")
    op.drop_table("credit_card_profiles")
