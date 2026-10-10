# SPDX-License-Identifier: AGPL-3.0-or-later
"""NBP Table A mid rates, shared by every family of an instance (ADR-38, part B2c).

Public data: the same for everyone, so it lives once in the registry's schema
rather than in each family's ``currency_rates`` — which keeps the rates a
member typed and the ones recorded from their own transfers, since those say
something about the family's transactions.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import PublicBase
from kaleta.db.tenant_schemas import PUBLIC_SCHEMA


def _now() -> datetime:
    return datetime.now(UTC)


class NbpRate(PublicBase):
    """1 ``currency`` = ``mid`` PLN on ``date``; the PLN → ``currency`` rate is ``1 / mid``."""

    __tablename__ = "nbp_rates"
    __table_args__ = (
        UniqueConstraint("date", "currency", name="uq_nbp_rates_date_currency"),
        {"schema": PUBLIC_SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    mid: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=6), nullable=False)
    table_no: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return f"<NbpRate {self.date} 1 {self.currency} = {self.mid} PLN>"
