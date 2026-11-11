"""gifts become a yearly grid: people, occasions, cells

The flat ``gifts`` list ("person · occasion · amount" as free text) is
replaced by ``gift_people`` (rows), ``gift_occasions`` (columns) and
``gift_cells`` (one amount per person, occasion and year). The owner chose to
start from zero (plan ``gifts-grid``), so old rows are not migrated: links
from transactions are cleared and ``transactions.gift_id`` now points at a
cell. The six default occasions are created by the app on first use, in the
user's language, not here.

No schema is hard-coded: a per-family run is rewritten by
``schema_translate_map`` in ``alembic/env.py`` (ADR-35/ADR-38).

Revision ID: d4f2a9c61e07
Revises: b2e9f41a7c38
Create Date: 2026-11-11 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d4f2a9c61e07"
down_revision = "b2e9f41a7c38"
branch_labels = None
depends_on = None


def _owned_columns() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _named_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        # ``EncryptedText``: ciphertext, like other user text.
        sa.Column("name", sa.LargeBinary(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_owned_columns(),
    )


def _clear_gift_links() -> None:
    # Core, not ``text()``: ``schema_translate_map`` rewrites only statements
    # built on a table object, and this runs once per family schema.
    transactions = sa.table("transactions", sa.column("gift_id", sa.Integer()))
    op.execute(
        sa.update(transactions).where(transactions.c.gift_id.is_not(None)).values(gift_id=None)
    )


def upgrade() -> None:
    _clear_gift_links()
    op.drop_constraint("transactions_gift_id_fkey", "transactions", type_="foreignkey")
    op.drop_table("gifts")

    _named_table("gift_people")
    _named_table("gift_occasions")
    op.create_table(
        "gift_cells",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column(
            "person_id",
            sa.Integer(),
            sa.ForeignKey("gift_people.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "occasion_id",
            sa.Integer(),
            sa.ForeignKey("gift_occasions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("note", sa.LargeBinary(), nullable=True),
        *_owned_columns(),
        sa.UniqueConstraint("year", "person_id", "occasion_id", name="uq_gift_cells_slot"),
    )
    op.create_index("ix_gift_cells_person_id", "gift_cells", ["person_id"])
    op.create_index("ix_gift_cells_occasion_id", "gift_cells", ["occasion_id"])

    op.create_foreign_key(
        "transactions_gift_id_fkey",
        "transactions",
        "gift_cells",
        ["gift_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # The grid has no faithful flat form; going back drops it, as going
    # forward dropped the list.
    _clear_gift_links()
    op.drop_constraint("transactions_gift_id_fkey", "transactions", type_="foreignkey")
    op.drop_index("ix_gift_cells_occasion_id", table_name="gift_cells")
    op.drop_index("ix_gift_cells_person_id", table_name="gift_cells")
    op.drop_table("gift_cells")
    op.drop_table("gift_occasions")
    op.drop_table("gift_people")

    op.create_table(
        "gifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("person", sa.LargeBinary(), nullable=False),
        sa.Column("occasion", sa.LargeBinary(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        *_owned_columns(),
    )
    op.create_foreign_key(
        "transactions_gift_id_fkey",
        "transactions",
        "gifts",
        ["gift_id"],
        ["id"],
        ondelete="SET NULL",
    )
