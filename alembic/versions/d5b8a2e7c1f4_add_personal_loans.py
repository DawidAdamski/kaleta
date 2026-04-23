"""add personal loans tables

Revision ID: d5b8a2e7c1f4
Revises: b6d9c5a2f8e3
Create Date: 2026-04-23 16:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d5b8a2e7c1f4"
down_revision = "b6d9c5a2f8e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "counterparties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("name", name="uq_counterparty_name"),
    )

    op.create_table(
        "personal_loans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("counterparty_id", sa.Integer(), nullable=False),
        sa.Column(
            "direction",
            sa.Enum(
                "outgoing",
                "incoming",
                name="loandirection",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("principal", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="PLN",
        ),
        sa.Column("opened_at", sa.Date(), nullable=False),
        sa.Column("due_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "outstanding",
                "settled",
                name="loanstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="outstanding",
        ),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
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
            ["counterparty_id"],
            ["counterparties.id"],
            name="fk_personal_loans_counterparty_id",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "personal_loan_repayments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("loan_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("linked_transaction_id", sa.Integer(), nullable=True),
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
            ["loan_id"],
            ["personal_loans.id"],
            name="fk_personal_loan_repayments_loan_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["linked_transaction_id"],
            ["transactions.id"],
            name="fk_personal_loan_repayments_linked_transaction_id",
            ondelete="SET NULL",
        ),
    )


def downgrade() -> None:
    op.drop_table("personal_loan_repayments")
    op.drop_table("personal_loans")
    op.drop_table("counterparties")
