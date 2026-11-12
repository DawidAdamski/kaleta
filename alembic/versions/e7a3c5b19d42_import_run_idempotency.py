"""import runs remember an API idempotency key and a keyed hash of the file

``POST /api/v1/imports`` (plan ``import-api-endpoint``) replays a request that
repeats its ``Idempotency-Key`` and refuses the same statement twice for one
account. Both columns are nullable: runs from the import page, and every run
before this revision, have neither.

No schema is hard-coded: a per-family run is rewritten by
``schema_translate_map`` in ``alembic/env.py`` (ADR-35/ADR-38).

Revision ID: e7a3c5b19d42
Revises: d4f2a9c61e07
Create Date: 2026-11-12 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e7a3c5b19d42"
down_revision = "d4f2a9c61e07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("import_runs", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.add_column("import_runs", sa.Column("file_hmac", sa.String(64), nullable=True))
    op.create_index("ix_import_runs_idempotency_key", "import_runs", ["idempotency_key"])
    op.create_index("ix_import_runs_file_hmac", "import_runs", ["file_hmac"])


def downgrade() -> None:
    op.drop_index("ix_import_runs_file_hmac", table_name="import_runs")
    op.drop_index("ix_import_runs_idempotency_key", table_name="import_runs")
    op.drop_column("import_runs", "file_hmac")
    op.drop_column("import_runs", "idempotency_key")
