# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.db.types import EncryptedText
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin


class Gift(TimestampMixin, UserOwnedMixin, Base):
    """One planned gift: who it is for, the occasion, and how much to set aside.

    One row per person+occasion so a later slice can mark an individual gift
    bought and link the transaction that paid for it (KAL-GFT-003). ``person``
    and ``occasion`` are user text, so they are encrypted — grouping by person
    therefore happens in Python, not SQL.
    """

    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    person: Mapped[str] = mapped_column(EncryptedText("gifts.person"), nullable=False)
    occasion: Mapped[str] = mapped_column(EncryptedText("gifts.occasion"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)

    def __repr__(self) -> str:
        return f"<Gift id={self.id}>"
