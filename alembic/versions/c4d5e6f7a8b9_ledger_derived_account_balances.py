# SPDX-License-Identifier: AGPL-3.0-or-later
"""Account balances follow the ledger.

``accounts.balance`` becomes ``accounts.opening_balance``: the balance is
now opening balance + the signed sum of the account's transactions, computed
on read. A transfer leg gains ``transfer_direction`` (``OUT``/``IN``), since
``amount`` is unsigned and a ``TRANSFER`` row otherwise does not say which
way the money went.

Backfills, in this order:

1. Direction of existing transfer legs. A linked pair: the lower id is the
   outgoing leg, the order ``create_transfer`` saves them in. An unlinked
   leg (an mBank import before this revision) has no recoverable direction
   and gets ``OUT``.
2. Opening balance, anchored: old balance − signed ledger. The derived
   balance therefore equals what every user saw before upgrading, whatever
   step 1 guessed. A wrong guess only shows if that old row is edited later.

Revision ID: c4d5e6f7a8b9
Revises: 3b168fa7bb71
Create Date: 2026-09-30 12:00:00.000000
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "3b168fa7bb71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# Enums are stored by member name (no ``values_callable`` on the models).
# Constant SQL, no user input: interpolated into the two UPDATEs below.
_SIGNED_LEDGER = """
    SELECT COALESCE(SUM(CASE
        WHEN t.type = 'INCOME' THEN t.amount
        WHEN t.type = 'EXPENSE' THEN -t.amount
        WHEN t.transfer_direction = 'IN' THEN t.amount
        WHEN t.transfer_direction = 'OUT' THEN -t.amount
        ELSE 0
    END), 0)
    FROM transactions t
    WHERE t.account_id = accounts.id
"""

_CHECK_NAME = "ck_transactions_transfer_direction"
_CHECK_SQL = "(type = 'TRANSFER') = (transfer_direction IS NOT NULL)"


def upgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "transfer_direction",
                sa.Enum("OUT", "IN", name="transferdirection", native_enum=False),
                nullable=True,
            )
        )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE transactions SET transfer_direction = CASE "
            "WHEN id < linked_transaction_id THEN 'OUT' ELSE 'IN' END "
            "WHERE type = 'TRANSFER' AND linked_transaction_id IS NOT NULL"
        )
    )
    unlinked = bind.execute(
        sa.text(
            "UPDATE transactions SET transfer_direction = 'OUT' "
            "WHERE type = 'TRANSFER' AND transfer_direction IS NULL"
        )
    ).rowcount
    logger.info("transfer_direction: %s unlinked transfer leg(s) backfilled as OUT", unlinked)

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.create_check_constraint(_CHECK_NAME, _CHECK_SQL)

    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.alter_column(
            "balance",
            new_column_name="opening_balance",
            existing_type=sa.Numeric(precision=15, scale=2),
            existing_nullable=False,
        )

    bind.execute(
        sa.text(f"UPDATE accounts SET opening_balance = opening_balance - ({_SIGNED_LEDGER})")
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Back to a stored figure: the balance as it stands today.
    bind.execute(
        sa.text(f"UPDATE accounts SET opening_balance = opening_balance + ({_SIGNED_LEDGER})")
    )
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.alter_column(
            "opening_balance",
            new_column_name="balance",
            existing_type=sa.Numeric(precision=15, scale=2),
            existing_nullable=False,
        )

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_constraint(_CHECK_NAME, type_="check")
        batch_op.drop_column("transfer_direction")
