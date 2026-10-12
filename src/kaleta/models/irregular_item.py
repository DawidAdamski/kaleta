# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.db.types import EncryptedText
from kaleta.models.mixins import TimestampMixin, UserOwnedMixin


class IrregularItem(TimestampMixin, UserOwnedMixin, Base):
    """One yearly cost an irregular-expenses fund saves for (car insurance, property tax).

    ``due_month`` (1–12) is when it is usually paid; ``None`` for a cost
    without a month. ``category_id`` is what a payment of it is booked under.
    """

    __tablename__ = "irregular_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(
        ForeignKey("reserve_funds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(EncryptedText("irregular_items.name"), nullable=False)
    yearly_amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    due_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<IrregularItem id={self.id} fund_id={self.fund_id}>"
