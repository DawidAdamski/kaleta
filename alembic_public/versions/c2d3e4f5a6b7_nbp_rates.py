# SPDX-License-Identifier: AGPL-3.0-or-later
"""NBP Table A mid rates, once per instance (ADR-38, postgres-only part B2c).

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-10 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"


def upgrade() -> None:
    op.create_table(
        "nbp_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("mid", sa.Numeric(precision=15, scale=6), nullable=False),
        sa.Column("table_no", sa.String(length=32), nullable=False, server_default=""),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("date", "currency", name="uq_nbp_rates_date_currency"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("nbp_rates", schema=SCHEMA)
