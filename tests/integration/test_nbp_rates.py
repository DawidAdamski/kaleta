# SPDX-License-Identifier: AGPL-3.0-or-later
"""NBP Table A rates, fetched once per instance into ``public.nbp_rates``.

Covers: KAL-FXR-001, KAL-FXR-002, KAL-FXR-003, KAL-FXR-004
"""

from __future__ import annotations

import asyncio
import datetime
import json
import urllib.error
from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import ExternalServiceError
from kaleta.models.nbp_rate import NbpRate
from kaleta.schemas.currency_rate import CurrencyRateCreate, RateSource
from kaleta.services.currency_rate_service import CurrencyRateService
from kaleta.services.nbp_rate_scheduler import NbpRateScheduler
from kaleta.services.nbp_rate_service import NbpRateService

# Literals from the KAL-FXR scenarios.
JULY_19 = datetime.date(2024, 7, 19)
JULY_22 = datetime.date(2024, 7, 22)
JULY_23 = datetime.date(2024, 7, 23)


def _table_a(effective: str = "2024-07-22", **mids: float) -> bytes:
    rates = mids or {"EUR": 4.25, "USD": 3.9}
    return json.dumps(
        [
            {
                "table": "A",
                "no": "140/A/NBP/2024",
                "effectiveDate": effective,
                "rates": [{"code": code, "mid": mid} for code, mid in rates.items()],
            }
        ]
    ).encode("utf-8")


def _service(session: AsyncSession, payload: bytes) -> NbpRateService:
    # The suite's session reaches `public` too: registry models name it.
    return NbpRateService(session, http_get=lambda _url: payload)


async def _nbp_rows(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(NbpRate))).scalar_one())


async def test_nbp_import_stores_one_mid_per_currency_for_the_instance(
    session: AsyncSession,
) -> None:
    """Covers: KAL-FXR-001"""
    result = await _service(session, _table_a()).import_latest()
    assert result.effective_date == JULY_22
    assert (result.currencies_stored, result.rows_written) == (2, 2)

    stored = {
        row.currency: row.mid
        for row in (await session.execute(select(NbpRate).where(NbpRate.date == JULY_22)))
        .scalars()
        .all()
    }
    assert stored == {"EUR": Decimal("4.250000"), "USD": Decimal("3.900000")}
    assert NbpRate.__table__.schema == "public"

    rates = CurrencyRateService(session)
    assert await rates.get_rate_on(JULY_22, "EUR", "PLN") == Decimal("4.250000")
    assert await rates.get_rate_on(JULY_22, "PLN", "EUR") == Decimal("0.235294")
    assert await rates.get_rate_on(JULY_22, "USD", "PLN") == Decimal("3.900000")
    assert await rates.get_rate_on(JULY_22, "PLN", "USD") == Decimal("0.256410")

    again = await _service(session, _table_a()).import_latest()
    assert again.rows_written == 0
    assert await _nbp_rows(session) == 2


async def test_nbp_import_offline_fails_soft(session: AsyncSession) -> None:
    """Covers: KAL-FXR-002"""

    def _offline(_url: str) -> bytes:
        raise urllib.error.URLError("Network is unreachable")

    with pytest.raises(ExternalServiceError, match="network unavailable"):
        await NbpRateService(session, http_get=_offline).import_latest()

    assert await _nbp_rows(session) == 0


async def test_a_familys_own_rate_wins_its_day_and_a_later_nbp_rate_wins_after(
    session: AsyncSession,
) -> None:
    """Covers: KAL-FXR-004"""
    await _service(session, _table_a(EUR=4.25)).import_latest()
    rates = CurrencyRateService(session)
    for day, rate in ((JULY_22, "4.3000"), (JULY_19, "4.1000")):
        await rates.create(
            CurrencyRateCreate(date=day, from_currency="EUR", to_currency="PLN", rate=rate)
        )

    assert await rates.get_rate_on(JULY_22, "EUR", "PLN") == Decimal("4.300000")

    await _service(session, _table_a("2024-07-23", EUR=4.28)).import_latest()
    assert await rates.get_rate_on(JULY_23, "EUR", "PLN") == Decimal("4.280000")

    history = await rates.load_rates_for_currencies({"EUR"}, "PLN")
    assert history["EUR"] == [
        (JULY_19, Decimal("4.100000")),
        (JULY_22, Decimal("4.300000")),
        (JULY_23, Decimal("4.280000")),
    ]

    listed = await rates.list_recent_for_pairs([("EUR", "PLN")])
    assert [(row.date, row.source) for row in listed] == [
        (JULY_23, RateSource.NBP),
        (JULY_22, RateSource.FAMILY),
        (JULY_22, RateSource.NBP),
        (JULY_19, RateSource.FAMILY),
    ]


@pytest_asyncio.fixture
async def _no_nbp_rows_left() -> AsyncIterator[None]:
    """The scheduler commits on a session of its own; take its rows back out."""
    yield
    async with AsyncSessionFactory.public() as public:
        await public.execute(delete(NbpRate))
        await public.commit()


async def test_the_instance_fetch_is_opt_in(
    monkeypatch: pytest.MonkeyPatch, _no_nbp_rows_left: None
) -> None:
    """Covers: KAL-FXR-003"""
    http_get = MagicMock(side_effect=AssertionError("NBP must not be called"))
    monkeypatch.setattr(settings, "nbp_fetch", False)
    with patch.object(NbpRateService, "default_http_get", http_get):
        NbpRateScheduler.start()
    assert NbpRateScheduler._task is None
    http_get.assert_not_called()

    # Switched on, one fetch fills the instance's table; a failure is only logged.
    monkeypatch.setattr(settings, "nbp_fetch", True)
    with patch.object(NbpRateService, "default_http_get", staticmethod(lambda _url: _table_a())):
        await NbpRateScheduler.fetch_once()
    offline = MagicMock(side_effect=ExternalServiceError("offline"))
    with patch.object(NbpRateService, "default_http_get", offline):
        await NbpRateScheduler.fetch_once()
    async with AsyncSessionFactory.public() as public:
        assert await _nbp_rows(public) == 2


async def test_an_import_racing_another_keeps_what_the_other_stored(session: AsyncSession) -> None:
    """Covers: KAL-FXR-001 — a row another fetch committed first is no conflict."""
    session.add(NbpRate(date=JULY_22, currency="EUR", mid=Decimal("4.25")))
    await session.flush()

    result = await _service(session, _table_a()).import_latest()

    assert (result.currencies_stored, result.rows_written) == (2, 1)
    assert await _nbp_rows(session) == 2


async def test_switched_on_the_fetch_runs_in_the_background_until_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers: KAL-FXR-003 — the start-up task, which then repeats once a day."""
    fetched = asyncio.Event()

    async def _fetch() -> None:
        fetched.set()

    monkeypatch.setattr(settings, "nbp_fetch", True)
    monkeypatch.setattr(NbpRateScheduler, "fetch_once", _fetch)
    NbpRateScheduler.start()
    try:
        task = NbpRateScheduler._task
        assert task is not None
        await asyncio.wait_for(fetched.wait(), timeout=5)
        assert not task.done()  # asleep until tomorrow's fetch
    finally:
        await NbpRateScheduler.stop()
    assert task.cancelled()
    assert NbpRateScheduler._task is None
