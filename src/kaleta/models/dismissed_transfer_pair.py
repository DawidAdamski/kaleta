# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class DismissedTransferPair(TimestampMixin, Base):
    """Two ledger rows the user has said are *not* one transfer.

    The import review suggests transfer pairs from amounts and dates alone;
    this table records "no, those two are unrelated" so the same pair is not
    offered again on the next import. Same idea as ``DismissedCandidate``,
    keyed by the two rows rather than by a pattern: a pair is a fact about
    two transactions, not about a merchant.

    The ids are stored lowest first, so a dismissal holds whichever way
    round the pair was offered. Deleting either row drops the dismissal.
    """

    __tablename__ = "dismissed_transfer_pairs"
    __table_args__ = (
        UniqueConstraint(
            "first_transaction_id",
            "second_transaction_id",
            name="uq_dismissed_transfer_pair",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    second_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<DismissedTransferPair id={self.id} "
            f"pair=({self.first_transaction_id}, {self.second_transaction_id})>"
        )
