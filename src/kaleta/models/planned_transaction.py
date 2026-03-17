from __future__ import annotations

import datetime
import enum
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin
from kaleta.models.transaction import TransactionType

if TYPE_CHECKING:
    from kaleta.models.account import Account
    from kaleta.models.category import Category


class RecurrenceFrequency(str, enum.Enum):  # noqa: UP042
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class PlannedTransaction(TimestampMixin, Base):
    __tablename__ = "planned_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, native_enum=False), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Recurrence
    frequency: Mapped[RecurrenceFrequency] = mapped_column(
        SAEnum(RecurrenceFrequency, native_enum=False), nullable=False
    )
    interval: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    account: Mapped[Account] = relationship("Account")  # type: ignore[name-defined]  # noqa: F821
    category: Mapped[Category | None] = relationship("Category")  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return f"<PlannedTransaction id={self.id} name={self.name!r} freq={self.frequency}>"
