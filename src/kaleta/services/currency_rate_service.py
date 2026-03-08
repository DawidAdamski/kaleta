from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.currency_rate import CurrencyRate
from kaleta.schemas.currency_rate import CurrencyRateCreate


class CurrencyRateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: CurrencyRateCreate) -> CurrencyRate:
        """Insert a new rate entry (duplicates on same date are allowed — most recent wins)."""
        entry = CurrencyRate(**data.model_dump())
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def record_transfer_rate(
        self,
        date: datetime.date,
        from_currency: str,
        to_currency: str,
        rate: Decimal,
    ) -> None:
        """Record a rate derived from a real transfer (both directions stored)."""
        if from_currency == to_currency:
            return
        await self.create(CurrencyRateCreate(
            date=date,
            from_currency=from_currency,
            to_currency=to_currency,
            rate=rate,
        ))
        # Also store the inverse so look-ups work in both directions
        if rate != Decimal("0"):
            await self.create(CurrencyRateCreate(
                date=date,
                from_currency=to_currency,
                to_currency=from_currency,
                rate=Decimal("1") / rate,
            ))

    async def get_rate_on(
        self,
        date: datetime.date,
        from_currency: str,
        to_currency: str,
    ) -> Decimal | None:
        """
        Return the most recent rate on or before `date` for the given pair.
        Returns None if no rate is found.
        """
        if from_currency == to_currency:
            return Decimal("1")
        stmt = (
            select(CurrencyRate)
            .where(
                CurrencyRate.from_currency == from_currency,
                CurrencyRate.to_currency == to_currency,
                CurrencyRate.date <= date,
            )
            .order_by(CurrencyRate.date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.scalars().first()
        if row:
            return row.rate
        # Try inverse direction
        stmt_inv = (
            select(CurrencyRate)
            .where(
                CurrencyRate.from_currency == to_currency,
                CurrencyRate.to_currency == from_currency,
                CurrencyRate.date <= date,
            )
            .order_by(CurrencyRate.date.desc())
            .limit(1)
        )
        result_inv = await self.session.execute(stmt_inv)
        row_inv = result_inv.scalars().first()
        if row_inv and row_inv.rate != Decimal("0"):
            return Decimal("1") / row_inv.rate
        return None

    async def get_latest_rate(
        self, from_currency: str, to_currency: str
    ) -> Decimal | None:
        """Return the most recent rate for the given pair regardless of date."""
        return await self.get_rate_on(
            datetime.date.today(), from_currency, to_currency
        )

    async def load_rates_for_currencies(
        self,
        currencies: set[str],
        to_currency: str,
    ) -> dict[str, list[tuple[datetime.date, Decimal]]]:
        """
        Load all historical rates for the given set of currencies → to_currency.
        Returns {from_currency: [(date, rate), ...]} sorted ascending by date.
        Used for batch lookups in NetWorthService.
        """
        if not currencies:
            return {}
        result = await self.session.execute(
            select(CurrencyRate)
            .where(
                CurrencyRate.from_currency.in_(currencies),
                CurrencyRate.to_currency == to_currency,
            )
            .order_by(CurrencyRate.date.asc())
        )
        rows = result.scalars().all()
        history: dict[str, list[tuple[datetime.date, Decimal]]] = {c: [] for c in currencies}
        for row in rows:
            history[row.from_currency].append((row.date, row.rate))

        # For any currency with no direct entries, try inverse
        missing = {c for c, entries in history.items() if not entries}
        if missing:
            result_inv = await self.session.execute(
                select(CurrencyRate)
                .where(
                    CurrencyRate.from_currency == to_currency,
                    CurrencyRate.to_currency.in_(missing),
                )
                .order_by(CurrencyRate.date.asc())
            )
            for row in result_inv.scalars().all():
                if row.rate != Decimal("0"):
                    history[row.to_currency].append((row.date, Decimal("1") / row.rate))
            for cur in missing:
                history[cur].sort(key=lambda x: x[0])

        return history

    async def list_for_pair(
        self, from_currency: str, to_currency: str
    ) -> list[CurrencyRate]:
        result = await self.session.execute(
            select(CurrencyRate)
            .where(
                CurrencyRate.from_currency == from_currency,
                CurrencyRate.to_currency == to_currency,
            )
            .order_by(CurrencyRate.date.desc())
        )
        return list(result.scalars().all())

    async def list_pairs(self) -> list[tuple[str, str]]:
        """Return all unique (from_currency, to_currency) pairs in the DB."""
        result = await self.session.execute(
            select(CurrencyRate.from_currency, CurrencyRate.to_currency).distinct()
        )
        return [(r.from_currency, r.to_currency) for r in result.all()]

    async def delete(self, rate_id: int) -> bool:
        result = await self.session.execute(
            select(CurrencyRate).where(CurrencyRate.id == rate_id)
        )
        row = result.scalars().first()
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.commit()
        return True
