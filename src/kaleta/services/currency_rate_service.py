# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exchange rates as a family sees them: its own, and the instance's NBP rates.

Two tables answer (ADR-38, part B2c): the family's ``currency_rates`` — rates
a member typed and the ones recorded from their transfers — and
``public.nbp_rates``, the NBP Table A mids every family shares. A lookup takes
the latest rate on or before the date from either; on the same date the
family's own wins. NBP covers only pairs with PLN on one side.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.currency_rate import CurrencyRate
from kaleta.models.nbp_rate import NbpRate
from kaleta.schemas.currency_rate import CurrencyRateCreate, CurrencyRateResponse, RateSource

PLN = "PLN"
#: The scale ``currency_rates.rate`` keeps, so a derived inverse reads as a stored one did.
_RATE_SCALE = Decimal("0.000001")


def _nbp_rate(row: NbpRate, from_currency: str) -> Decimal:
    """1 ``from_currency`` in the other currency of the pair, from one NBP mid."""
    if from_currency == PLN:
        return (Decimal("1") / row.mid).quantize(_RATE_SCALE)
    return row.mid


def _nbp_currency(from_currency: str, to_currency: str) -> str | None:
    """The non-PLN side of a pair NBP can answer, or ``None``."""
    if from_currency == to_currency or PLN not in (from_currency, to_currency):
        return None
    return to_currency if from_currency == PLN else from_currency


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
        await self.create(
            CurrencyRateCreate(
                date=date,
                from_currency=from_currency,
                to_currency=to_currency,
                rate=rate,
            )
        )
        # Also store the inverse so look-ups work in both directions
        if rate != Decimal("0"):
            await self.create(
                CurrencyRateCreate(
                    date=date,
                    from_currency=to_currency,
                    to_currency=from_currency,
                    rate=Decimal("1") / rate,
                )
            )

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
        own = await self._family_rate_on(date, from_currency, to_currency)
        nbp = await self._nbp_rate_on(date, from_currency, to_currency)
        if own is None or (nbp is not None and nbp[0] > own[0]):
            return nbp[1] if nbp is not None else None
        return own[1]

    async def _family_rate_on(
        self, date: datetime.date, from_currency: str, to_currency: str
    ) -> tuple[datetime.date, Decimal] | None:
        """The family's own rate for the pair, direct first, else inverted."""
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
        row = (await self.session.execute(stmt)).scalars().first()
        if row:
            return row.date, row.rate
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
        row_inv = (await self.session.execute(stmt_inv)).scalars().first()
        if row_inv and row_inv.rate != Decimal("0"):
            return row_inv.date, Decimal("1") / row_inv.rate
        return None

    async def _nbp_rate_on(
        self, date: datetime.date, from_currency: str, to_currency: str
    ) -> tuple[datetime.date, Decimal] | None:
        currency = _nbp_currency(from_currency, to_currency)
        if currency is None:
            return None
        row = (
            (
                await self.session.execute(
                    select(NbpRate)
                    .where(NbpRate.currency == currency, NbpRate.date <= date)
                    .order_by(NbpRate.date.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if row is None or row.mid == Decimal("0"):
            return None
        return row.date, _nbp_rate(row, from_currency)

    async def get_latest_rate(self, from_currency: str, to_currency: str) -> Decimal | None:
        """Return the most recent rate for the given pair regardless of date."""
        return await self.get_rate_on(datetime.date.today(), from_currency, to_currency)

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

        await self._merge_nbp_history(history, to_currency)
        return history

    async def _merge_nbp_history(
        self, history: dict[str, list[tuple[datetime.date, Decimal]]], to_currency: str
    ) -> None:
        """Add the instance's NBP rates under the family's, which win on their dates."""
        wanted = {
            currency: nbp
            for currency in history
            if (nbp := _nbp_currency(currency, to_currency)) is not None
        }
        if not wanted:
            return
        rows = (
            await self.session.execute(
                select(NbpRate).where(NbpRate.currency.in_(set(wanted.values())))
            )
        ).scalars()
        by_currency: dict[str, list[NbpRate]] = {}
        for row in rows:
            if row.mid != Decimal("0"):
                by_currency.setdefault(row.currency, []).append(row)
        for currency, nbp in wanted.items():
            merged = {row.date: _nbp_rate(row, currency) for row in by_currency.get(nbp, [])}
            merged.update(dict(history[currency]))
            history[currency] = sorted(merged.items())

    @staticmethod
    def build_relevant_pairs(
        default_currency: str,
        account_currencies: set[str],
        existing_pairs: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        """Build FX pairs needed for accounts whose currency differs from the default."""
        foreign_currencies = sorted(c for c in account_currencies if c != default_currency)
        relevant_pairs = [(fc, tc) for (fc, tc) in existing_pairs if tc == default_currency]
        existing_froms = {fc for (fc, _) in relevant_pairs}
        for currency in foreign_currencies:
            if currency not in existing_froms:
                relevant_pairs.append((currency, default_currency))
        return relevant_pairs

    async def list_recent_for_pairs(
        self,
        pairs: list[tuple[str, str]],
        *,
        per_pair: int = 5,
    ) -> list[CurrencyRateResponse]:
        """Return recent rate rows for each pair, sorted newest-first overall.

        The family's rows and the instance's NBP rows for that pair, the
        latter marked ``source=nbp``.
        """
        all_rows: list[CurrencyRateResponse] = []
        for from_currency, to_currency in pairs:
            rows = [
                CurrencyRateResponse.model_validate(row)
                for row in await self.list_for_pair(from_currency, to_currency)
            ]
            rows.extend(await self._nbp_rows_for_pair(from_currency, to_currency, per_pair))
            rows.sort(key=lambda row: (row.date, row.source is RateSource.FAMILY), reverse=True)
            all_rows.extend(rows[:per_pair])
        all_rows.sort(key=lambda row: row.date, reverse=True)
        return all_rows

    async def _nbp_rows_for_pair(
        self, from_currency: str, to_currency: str, limit: int
    ) -> list[CurrencyRateResponse]:
        currency = _nbp_currency(from_currency, to_currency)
        if currency is None:
            return []
        rows = (
            await self.session.execute(
                select(NbpRate)
                .where(NbpRate.currency == currency)
                .order_by(NbpRate.date.desc())
                .limit(limit)
            )
        ).scalars()
        return [
            CurrencyRateResponse(
                id=row.id,
                date=row.date,
                from_currency=from_currency,
                to_currency=to_currency,
                rate=_nbp_rate(row, from_currency),
                created_at=row.fetched_at,
                updated_at=row.fetched_at,
                source=RateSource.NBP,
            )
            for row in rows
            if row.mid != Decimal("0")
        ]

    async def create_with_inverse(
        self,
        data: CurrencyRateCreate,
        *,
        also_inverse: bool = True,
    ) -> None:
        """Insert a rate and optionally its inverse for bidirectional lookups."""
        await self.create(data)
        if also_inverse:
            await self.create(
                CurrencyRateCreate(
                    date=data.date,
                    from_currency=data.to_currency,
                    to_currency=data.from_currency,
                    rate=Decimal("1") / data.rate,
                )
            )

    async def list_for_pair(self, from_currency: str, to_currency: str) -> list[CurrencyRate]:
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
        result = await self.session.execute(select(CurrencyRate).where(CurrencyRate.id == rate_id))
        row = result.scalars().first()
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.commit()
        return True
