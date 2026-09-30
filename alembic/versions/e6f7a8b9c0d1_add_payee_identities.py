# SPDX-License-Identifier: AGPL-3.0-or-later
"""Payee identities, merge dismissals and the auto-merge undo log.

Every existing payee gets one identity: its own name.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-30 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def _identity_key(pattern: str) -> str:
    # Frozen copy of kaleta.models.payee_identity.identity_key — a migration
    # must not change meaning when the app code does.
    return " ".join(pattern.split()).casefold()


def upgrade() -> None:
    identities = op.create_table(
        "payee_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payee_id", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(length=200), nullable=False),
        sa.Column("pattern_key", sa.String(length=200), nullable=False),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["payee_id"],
            ["payees.id"],
            name="fk_payee_identities_payee_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_payee_identities_payee_id", "payee_identities", ["payee_id"])
    op.create_index("ix_payee_identities_pattern", "payee_identities", ["pattern"])
    op.create_index("ix_payee_identities_pattern_key", "payee_identities", ["pattern_key"])

    op.create_table(
        "dismissed_payee_merges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_payee_id", sa.Integer(), nullable=False),
        sa.Column("second_payee_id", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["first_payee_id"],
            ["payees.id"],
            name="fk_dismissed_payee_merges_first_payee_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["second_payee_id"],
            ["payees.id"],
            name="fk_dismissed_payee_merges_second_payee_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("first_payee_id", "second_payee_id", name="uq_dismissed_payee_merge"),
    )

    op.create_table(
        "payee_auto_merges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keeper_id", sa.Integer(), nullable=False),
        sa.Column("merged_name", sa.String(length=200), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["keeper_id"],
            ["payees.id"],
            name="fk_payee_auto_merges_keeper_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_payee_auto_merges_keeper_id", "payee_auto_merges", ["keeper_id"])

    # Backfill: one identity per payee, pattern = the payee's name. The key
    # is computed in Python — SQL lower() does not fold Polish letters.
    bind = op.get_bind()
    payees = bind.execute(sa.text("SELECT id, name FROM payees ORDER BY id")).all()
    if payees:
        op.bulk_insert(
            identities,
            [
                {
                    "payee_id": payee_id,
                    "pattern": " ".join(name.split()),
                    "pattern_key": _identity_key(name),
                    "case_sensitive": False,
                }
                for payee_id, name in payees
            ],
        )


def downgrade() -> None:
    op.drop_index("ix_payee_auto_merges_keeper_id", table_name="payee_auto_merges")
    op.drop_table("payee_auto_merges")
    op.drop_table("dismissed_payee_merges")
    op.drop_index("ix_payee_identities_pattern_key", table_name="payee_identities")
    op.drop_index("ix_payee_identities_pattern", table_name="payee_identities")
    op.drop_index("ix_payee_identities_payee_id", table_name="payee_identities")
    op.drop_table("payee_identities")
