# SPDX-License-Identifier: AGPL-3.0-or-later
"""add dismissed_candidate_patterns.kind column

The unplanned-expenses radar reuses the dismissal table; ``kind`` keeps a
"not a subscription" decision from silencing the radar (and vice versa) and
joins the uniqueness key so both detectors can dismiss the same source.

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-09-04 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "k5l6m7n8o9p0"
down_revision = "j4k5l6m7n8o9"
branch_labels = None
depends_on = None

_KIND = sa.Enum(
    "SUBSCRIPTION",
    "UNPLANNED",
    name="dismissedcandidatekind",
    native_enum=False,
)


def upgrade() -> None:
    with op.batch_alter_table("dismissed_candidate_patterns", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kind", _KIND, nullable=False, server_default="SUBSCRIPTION"))
        batch_op.drop_constraint("uq_dismissed_candidate_pattern", type_="unique")
        batch_op.create_unique_constraint(
            "uq_dismissed_candidate_pattern",
            ["payee_id", "merchant_key", "amount_bucket", "kind"],
        )


def downgrade() -> None:
    # The radar's dismissals have nowhere to live once ``kind`` is gone, and
    # leaving them would collide: a source dismissed in both panels holds a
    # SUBSCRIPTION row and an UNPLANNED row that differ only by the column
    # being dropped, so re-creating the narrower unique constraint would fail
    # on a duplicate key. Dropping them is also the honest reading — the
    # schema being restored has no concept of an unplanned dismissal.
    op.execute("DELETE FROM dismissed_candidate_patterns WHERE kind = 'UNPLANNED'")
    with op.batch_alter_table("dismissed_candidate_patterns", schema=None) as batch_op:
        batch_op.drop_constraint("uq_dismissed_candidate_pattern", type_="unique")
        batch_op.create_unique_constraint(
            "uq_dismissed_candidate_pattern",
            ["payee_id", "merchant_key", "amount_bucket"],
        )
        batch_op.drop_column("kind")
