"""make audit_log.timestamp and personal_loans.settled_at tz-aware

The last two family timestamps still held as ``timestamp without time zone``
move to ``timestamptz``, matching their models (now ``DateTime(timezone=True)``)
and the rest of the schema. ``postgres-only`` part B3 dropped the "SQLite hands
back naive datetimes" fallbacks only where the column was already
``timestamptz``; these two were left behind.

* ``audit_log.timestamp`` is written by ``func.now()`` under a UTC session.
* ``personal_loans.settled_at`` was written as naive UTC
  (``datetime.now(UTC).replace(tzinfo=None)``); the service now writes an
  aware UTC datetime.

Both stored values are UTC, so ``AT TIME ZONE 'UTC'`` names the same instant
each way, independent of the session ``TimeZone`` at migration time — the same
argument ``9f318d21f98a`` makes. No schema is hard-coded: a per-family run is
rewritten by ``schema_translate_map`` in ``alembic/env.py`` exactly as for
every other migration (ADR-35/ADR-38). ``reserve_funds.archived_at`` is left
naive on purpose — its model is a plain ``DateTime()``.

Revision ID: a1c7e2f84b50
Revises: 9f318d21f98a
Create Date: 2026-10-24 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c7e2f84b50"
down_revision: str | Sequence[str] | None = "9f318d21f98a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "audit_log",
        "timestamp",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "personal_loans",
        "settled_at",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="settled_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "personal_loans",
        "settled_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=True,
        postgresql_using="settled_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "audit_log",
        "timestamp",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=False,
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )
