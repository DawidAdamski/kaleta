"""reconcile model/db drift: fk ondelete, timestamp tz, indexes

Brings the schema back in line with the models (the source of truth), so
``alembic check`` reports no drift on a fresh head database:

* ``fk_categories_parent_id`` gains ``ON DELETE SET NULL`` — the delete
  behaviour ``Category.parent_id`` declares. The constraint predates the
  ``ondelete`` and was created without one.
* ``currency_rates``, ``saved_reports`` and ``tags`` carry their
  ``created_at``/``updated_at`` as ``timestamp without time zone`` from the
  migrations that created them; ``TimestampMixin`` declares
  ``DateTime(timezone=True)``. They become ``timestamptz``.
* ``reserve_funds.archived_at`` is the reverse: the DB holds ``timestamptz``
  but ``ReserveFund.archived_at`` declares a plain ``DateTime()``. It becomes
  ``timestamp without time zone`` — reconciling toward the model, which is
  what ``ReserveFundService`` writes (``datetime.now(UTC).replace(tzinfo=None)``).
* ``ix_gifts_user_id`` is dropped. ``gifts`` are listed per family schema and
  fetched by ``id``; ``user_id`` is never a query predicate, and no other
  ``UserOwnedMixin`` table indexes it. (The two ``import_runs`` indexes that
  also drifted are kept — ``account_id`` and ``created_at`` are real query
  predicates — by declaring them on ``ImportRun`` instead, so they need no op.)

Timestamp conversions are non-shifting: every stored value is UTC. ORM writes
go through ``DateTime(timezone=True)`` bind params (asyncpg sends ``timestamptz``,
Postgres casts to the column under the UTC session ``TimeZone``);
``server_default`` is ``now()``/``CURRENT_TIMESTAMP`` cast the same way; and
``archived_at`` is written as naive UTC. ``AT TIME ZONE 'UTC'`` therefore names
the instant each way, independent of the session ``TimeZone`` at migration time.
No schema is hard-coded: a per-family run is rewritten by ``schema_translate_map``
in ``alembic/env.py`` exactly as for every other migration (ADR-35/ADR-38).

Revision ID: 9f318d21f98a
Revises: d4f7a9c2e1b6
Create Date: 2026-10-22 00:11:44.603906

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f318d21f98a"
down_revision: str | Sequence[str] | None = "d4f7a9c2e1b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, column) pairs whose timestamps move from naive to tz-aware.
_TO_TIMESTAMPTZ: tuple[tuple[str, str, bool], ...] = (
    ("currency_rates", "created_at", False),
    ("currency_rates", "updated_at", False),
    ("saved_reports", "created_at", False),
    ("saved_reports", "updated_at", False),
    ("tags", "created_at", False),
    ("tags", "updated_at", False),
)


def upgrade() -> None:
    """Upgrade schema."""
    # Categories self-FK: align the DB with ``Category.parent_id``'s SET NULL.
    op.drop_constraint("fk_categories_parent_id", "categories", type_="foreignkey")
    op.create_foreign_key(
        "fk_categories_parent_id",
        "categories",
        "categories",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # created_at/updated_at: naive ``timestamp`` → ``timestamptz`` (values are UTC).
    for table, column, _ in _TO_TIMESTAMPTZ:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=False),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )

    # reserve_funds.archived_at: ``timestamptz`` → naive ``timestamp`` (model is plain).
    op.alter_column(
        "reserve_funds",
        "archived_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=True,
        postgresql_using="archived_at AT TIME ZONE 'UTC'",
    )

    # gifts.user_id is never queried: drop the stray index (kept nowhere on the model).
    op.drop_index("ix_gifts_user_id", table_name="gifts")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_index("ix_gifts_user_id", "gifts", ["user_id"])

    op.alter_column(
        "reserve_funds",
        "archived_at",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="archived_at AT TIME ZONE 'UTC'",
    )

    for table, column, _ in _TO_TIMESTAMPTZ:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(timezone=False),
            existing_nullable=False,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )

    op.drop_constraint("fk_categories_parent_id", "categories", type_="foreignkey")
    op.create_foreign_key(
        "fk_categories_parent_id",
        "categories",
        "categories",
        ["parent_id"],
        ["id"],
    )
