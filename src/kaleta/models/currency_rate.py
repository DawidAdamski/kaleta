from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class CurrencyRate(TimestampMixin, Base):
    """Historical exchange rate: 1 from_currency = rate to_currency units on a given date."""

    __tablename__ = "currency_rates"
    __table_args__ = (Index("ix_currency_rates_lookup", "from_currency", "to_currency", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=6), nullable=False)

    def __repr__(self) -> str:
        return f"<CurrencyRate {self.date} 1 {self.from_currency} = {self.rate} {self.to_currency}>"
