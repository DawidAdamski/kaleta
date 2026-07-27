# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for NBP Table A import (mocked HTTP — never hits live NBP)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ExternalServiceError, ValidationError
from kaleta.services.currency_rate_service import CurrencyRateService
from kaleta.services.nbp_rate_service import NbpRateService


def _table_a_bytes(
    *,
    effective_date: str = "2024-07-22",
    table_no: str = "140/A/NBP/2024",
    rates: list[dict[str, object]] | None = None,
) -> bytes:
    if rates is None:
        rates = [
            {"currency": "euro", "code": "EUR", "mid": 4.25},
            {"currency": "dolar amerykański", "code": "USD", "mid": 3.9},
        ]
    payload = [
        {
            "table": "A",
            "no": table_no,
            "effectiveDate": effective_date,
            "rates": rates,
        }
    ]
    return json.dumps(payload).encode("utf-8")


class TestNbpRateServiceParse:
    def test_parse_mids_extracts_codes(self) -> None:
        """Covers: KAL-FXR-001"""
        table = json.loads(_table_a_bytes())[0]
        effective, table_no, mids = NbpRateService.parse_mids(table)
        assert effective == "2024-07-22"
        assert table_no == "140/A/NBP/2024"
        assert mids["EUR"] == Decimal("4.25")
        assert mids["USD"] == Decimal("3.9")

    def test_parse_mids_rejects_empty_rates(self) -> None:
        with pytest.raises(ValidationError):
            NbpRateService.parse_mids({"effectiveDate": "2024-07-22", "no": "x", "rates": []})


class TestNbpRateServiceImport:
    @pytest.mark.asyncio
    async def test_import_stores_both_directions(self, session: AsyncSession) -> None:
        """Covers: KAL-FXR-001"""
        svc = NbpRateService(session, http_get=lambda _url: _table_a_bytes())
        result = await svc.import_latest()

        assert result.effective_date.isoformat() == "2024-07-22"
        assert result.currencies_stored == 2
        assert result.rows_written == 4

        rates = CurrencyRateService(session)
        eur_pln = await rates.list_for_pair("EUR", "PLN")
        pln_eur = await rates.list_for_pair("PLN", "EUR")
        usd_pln = await rates.list_for_pair("USD", "PLN")
        pln_usd = await rates.list_for_pair("PLN", "USD")

        assert len(eur_pln) == 1
        assert eur_pln[0].rate == Decimal("4.250000")
        assert pln_eur[0].rate == Decimal("0.235294")
        assert usd_pln[0].rate == Decimal("3.900000")
        assert pln_usd[0].rate == Decimal("0.256410")

    @pytest.mark.asyncio
    async def test_import_offline_raises_external_service_error(
        self, session: AsyncSession
    ) -> None:
        """Covers: KAL-FXR-002"""

        def _fail(_url: str) -> bytes:
            raise urllib.error.URLError("Network is unreachable")

        svc = NbpRateService(session, http_get=_fail)
        with pytest.raises(ExternalServiceError, match="network unavailable"):
            await svc.import_latest()

        pairs = await CurrencyRateService(session).list_pairs()
        assert pairs == []

    def test_default_http_get_maps_url_error(self) -> None:
        """Covers: KAL-FXR-002"""
        with (
            patch.object(
                urllib.request,
                "urlopen",
                side_effect=urllib.error.URLError("offline"),
            ),
            pytest.raises(ExternalServiceError, match="network unavailable"),
        ):
            NbpRateService.default_http_get("https://api.nbp.pl/api/exchangerates/tables/A/")
