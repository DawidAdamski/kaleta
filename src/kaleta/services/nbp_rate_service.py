# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetch NBP Table A mid rates into ``public.nbp_rates`` — once for the whole instance.

The table is the registry's (ADR-38, part B2c): exchange rates are public
data, the same for every family, and every family's lookups read them
(``CurrencyRateService``). Works on a *public* session.
"""

from __future__ import annotations

import datetime
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ExternalServiceError, ValidationError
from kaleta.models.nbp_rate import NbpRate
from kaleta.schemas.nbp import NbpFetchResult

logger = logging.getLogger(__name__)

HttpGet = Callable[[str], bytes]

NBP_TABLE_A_URL = "https://api.nbp.pl/api/exchangerates/tables/A/?format=json"
_DEFAULT_TIMEOUT_S = 15.0
_USER_AGENT = "Kaleta/0.1 (+https://github.com/dawidadamski/kaleta)"


class NbpRateService:
    """Import the latest NBP Table A publication into ``public.nbp_rates``."""

    def __init__(
        self,
        public: AsyncSession,
        *,
        http_get: HttpGet | None = None,
        url: str = NBP_TABLE_A_URL,
    ) -> None:
        self.session = public
        self._http_get = http_get or self.default_http_get
        self._url = url

    @staticmethod
    def default_http_get(url: str) -> bytes:
        """GET *url* with stdlib urllib (no API key). Raises ExternalServiceError offline."""
        # S310 audits the URL scheme; callers pass NBP_TABLE_A_URL, an https constant.
        request = urllib.request.Request(  # noqa: S310
            url,
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_DEFAULT_TIMEOUT_S) as response:  # noqa: S310
                return bytes(response.read())
        except TimeoutError as exc:
            raise ExternalServiceError(
                "NBP rate fetch timed out. Check your network and try again."
            ) from exc
        except urllib.error.HTTPError as exc:
            raise ExternalServiceError(
                f"NBP rate fetch failed (HTTP {exc.code}). Try again later."
            ) from exc
        except urllib.error.URLError as exc:
            raise ExternalServiceError(
                "NBP rate fetch failed — network unavailable. The app continues offline."
            ) from exc

    def fetch_table_a_payload(self) -> list[dict[str, Any]]:
        """Download and JSON-decode Table A. Raises ExternalServiceError / ValidationError."""
        try:
            raw = self._http_get(self._url)
        except ExternalServiceError:
            raise
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise ExternalServiceError(
                "NBP rate fetch failed — network unavailable. The app continues offline."
            ) from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("NBP response was not valid JSON.") from exc
        if not isinstance(payload, list) or not payload:
            raise ValidationError("NBP Table A response was empty or unexpected.")
        tables = [item for item in payload if isinstance(item, dict)]
        if not tables:
            raise ValidationError("NBP Table A response had an unexpected shape.")
        return tables

    @staticmethod
    def parse_mids(table: dict[str, Any]) -> tuple[str, str, dict[str, Decimal]]:
        """
        Extract (effective_date ISO, table_no, {code: mid}) from one Table A object.

        Mid is PLN per 1 unit of foreign currency.
        """
        effective = table.get("effectiveDate")
        if not isinstance(effective, str) or not effective:
            raise ValidationError("NBP Table A is missing effectiveDate.")
        table_no = str(table.get("no") or "")
        rates = table.get("rates")
        if not isinstance(rates, list) or not rates:
            raise ValidationError("NBP Table A contained no rates.")

        mids: dict[str, Decimal] = {}
        for entry in rates:
            if not isinstance(entry, dict):
                continue
            code = entry.get("code")
            mid_raw = entry.get("mid")
            if not isinstance(code, str) or not code:
                continue
            try:
                mid = Decimal(str(mid_raw))
            except (InvalidOperation, TypeError):
                continue
            if mid > 0:
                mids[code.upper()] = mid
        if not mids:
            raise ValidationError("NBP Table A contained no usable mid rates.")
        return effective, table_no, mids

    async def import_latest(self) -> NbpFetchResult:
        """Fetch the latest Table A and store one mid per currency for its date.

        Idempotent: a currency already stored for that date is left alone, so
        the daily fetch and the Settings button may both run on the same day.
        """
        payload = self.fetch_table_a_payload()
        effective_s, table_no, mids = self.parse_mids(payload[0])
        try:
            on_date = datetime.date.fromisoformat(effective_s)
        except ValueError as exc:
            raise ValidationError(f"NBP effectiveDate is invalid: {effective_s!r}") from exc

        mids.pop("PLN", None)
        stored = set(
            (
                await self.session.execute(select(NbpRate.currency).where(NbpRate.date == on_date))
            ).scalars()
        )
        fresh = {code: mid for code, mid in mids.items() if code not in stored}
        self.session.add_all(
            NbpRate(date=on_date, currency=code, mid=mid, table_no=table_no)
            for code, mid in fresh.items()
        )
        if fresh:
            await self.session.commit()
        logger.info(
            "Imported NBP Table A %s (%s): %s currencies, %s new",
            table_no or "?",
            on_date.isoformat(),
            len(mids),
            len(fresh),
        )
        return NbpFetchResult(
            effective_date=on_date,
            table_no=table_no,
            currencies_stored=len(mids),
            rows_written=len(fresh),
        )
