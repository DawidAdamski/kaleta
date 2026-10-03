# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.db.types import EncryptedJSON, EncryptedText
from kaleta.models.mixins import TimestampMixin


class DismissedPayeeMerge(TimestampMixin, Base):
    """Two payees the user has said are *not* the same merchant.

    The merge scan proposes pairs by name similarity alone; this records
    "no, keep those apart" so the pair is not proposed again. The ids are
    stored lowest first, so a dismissal holds whichever way round the pair
    was offered. Deleting either payee drops the dismissal.
    """

    __tablename__ = "dismissed_payee_merges"
    __table_args__ = (
        UniqueConstraint("first_payee_id", "second_payee_id", name="uq_dismissed_payee_merge"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_payee_id: Mapped[int] = mapped_column(
        ForeignKey("payees.id", ondelete="CASCADE"), nullable=False
    )
    second_payee_id: Mapped[int] = mapped_column(
        ForeignKey("payees.id", ondelete="CASCADE"), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<DismissedPayeeMerge id={self.id} "
            f"pair=({self.first_payee_id}, {self.second_payee_id})>"
        )


class PayeeAutoMerge(TimestampMixin, Base):
    """An automatic merge, kept so the user can undo it for a while.

    ``snapshot`` holds what the merge took away from the merged payee — its
    own fields, the ids of the identities it handed over and the ids of the
    rows re-pointed at the keeper — which is exactly what undo gives back.
    Deleting the keeper drops the record: there is nothing left to undo into.
    """

    __tablename__ = "payee_auto_merges"

    id: Mapped[int] = mapped_column(primary_key=True)
    keeper_id: Mapped[int] = mapped_column(
        ForeignKey("payees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    merged_name: Mapped[str] = mapped_column(
        EncryptedText("payee_auto_merges.merged_name"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    #: Carries the merged payee's name, identities and contact fields, so it
    #: is encrypted whole like any other user text.
    snapshot: Mapped[dict[str, Any]] = mapped_column(
        EncryptedJSON("payee_auto_merges.snapshot"), nullable=False
    )
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PayeeAutoMerge id={self.id} keeper_id={self.keeper_id} "
            f"merged_name={self.merged_name!r}>"
        )
