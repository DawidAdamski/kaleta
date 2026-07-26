# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for optional NBP Table A currency-rate import.

Covers: KAL-FXR-001, KAL-FXR-002, KAL-FXR-003
"""

from __future__ import annotations

import json
import urllib.error
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import setup_config
from kaleta.exceptions import ExternalServiceError
from kaleta.services.currency_rate_service import CurrencyRateService
from kaleta.services.nbp_rate_service import NbpRateService
from kaleta.services.nbp_startup import NbpStartupFetcher


def _table_a_payload() -> bytes:
    return json.dumps(
        [
            {
                "table": "A",
                "no": "140/A/NBP/2024",
                "effectiveDate": "2024-07-22",
                "rates": [
                    {"currency": "euro", "code": "EUR", "mid": 4.25},
                    {"currency": "dolar amerykański", "code": "USD", "mid": 3.9},
                ],
            }
        ]
    ).encode("utf-8")


@pytest.mark.asyncio
async def test_nbp_import_stores_both_directions(session: AsyncSession) -> None:
    """Covers: KAL-FXR-001

    Given the NBP Table A API returns mid 4.2500 for EUR and mid 3.9000 for USD
    on effective date 2024-07-22
    When I import the latest NBP rates
    Then currency_rates contains EUR→PLN at 4.250000 and PLN→EUR at 0.235294
    And currency_rates contains USD→PLN at 3.900000 and PLN→USD at 0.256410
    """
    result = await NbpRateService(session, http_get=lambda _u: _table_a_payload()).import_latest()
    assert result.effective_date.isoformat() == "2024-07-22"
    assert result.currencies_stored == 2

    rates = CurrencyRateService(session)
    assert (await rates.list_for_pair("EUR", "PLN"))[0].rate == Decimal("4.250000")
    assert (await rates.list_for_pair("PLN", "EUR"))[0].rate == Decimal("0.235294")
    assert (await rates.list_for_pair("USD", "PLN"))[0].rate == Decimal("3.900000")
    assert (await rates.list_for_pair("PLN", "USD"))[0].rate == Decimal("0.256410")


@pytest.mark.asyncio
async def test_nbp_import_offline_fails_soft(session: AsyncSession) -> None:
    """Covers: KAL-FXR-002

    Given the NBP Table A HTTP call raises a network error
    When I import the latest NBP rates
    Then an ExternalServiceError is raised with a clear offline message
    And no currency_rates rows are written
    """

    def _offline(_url: str) -> bytes:
        raise urllib.error.URLError("Network is unreachable")

    with pytest.raises(ExternalServiceError, match="network unavailable"):
        await NbpRateService(session, http_get=_offline).import_latest()

    assert await CurrencyRateService(session).list_pairs() == []


def test_nbp_fetch_on_startup_defaults_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers: KAL-FXR-003

    Given nbp_fetch_on_startup is unset in ~/.kaleta/config.json
    When the NBP startup fetcher starts
    Then no HTTP request is made to NBP
    And get_nbp_fetch_on_startup returns false
    """
    monkeypatch.setattr(setup_config, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(setup_config, "_CONFIG_FILE", tmp_path / "config.json")

    assert setup_config.get_nbp_fetch_on_startup() is False

    http_get = MagicMock(side_effect=AssertionError("live NBP must not be called"))
    with patch.object(NbpRateService, "default_http_get", http_get):
        NbpStartupFetcher._task = None
        NbpStartupFetcher.start()

    assert NbpStartupFetcher._task is None
    http_get.assert_not_called()
