# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/forecast/balance`` — an account's balance forecast.

Covers: KAL-API-019

The literals of KAL-API-019 (30 points, 20 / 5 distinct days, 404 / 422 / 401).
No test asserts a forecast number: the naive forecaster is pinned so results do
not depend on whether the ``forecast`` extra (Prophet) is installed.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.services.forecast_service as forecast_module
from kaleta.api import create_api_router
from kaleta.db.tenant_context import TenantContext
from kaleta.services.forecast_service import ForecastService, clear_forecast_cache
from kaleta.services.forecasters.naive_forecaster import NaiveForecaster
from tests.integration.conftest import create_account, create_category

F = "/api/v1/forecast/balance"
MONEY = re.compile(r"^-?\d+\.\d{2}$")


@pytest.fixture(autouse=True)
def _naive_and_clean_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    clear_forecast_cache()
    monkeypatch.setattr(forecast_module, "get_forecaster", NaiveForecaster)
    monkeypatch.setattr(forecast_module, "active_forecaster_model", lambda: "naive")
    yield
    clear_forecast_cache()


async def _account_with_days(client: AsyncClient, days: int) -> int:
    """'PKO Main' with an income and an expense on ``days`` distinct days in the last 60."""
    account = (await create_account(client, name="PKO Main", balance="5000.00"))["id"]
    salary = (await create_category(client, name="Wynagrodzenie", type="income"))["id"]
    food = (await create_category(client, name="Spożywcze", type="expense"))["id"]
    today = datetime.date.today()
    for n in range(days):
        day = (today - datetime.timedelta(days=2 + n * 2)).isoformat()
        for kind, cat, amount in (("income", salary, "300.00"), ("expense", food, "120.00")):
            resp = await client.post(
                "/api/v1/transactions/",
                json={
                    "account_id": account,
                    "category_id": cat,
                    "amount": amount,
                    "type": kind,
                    "date": day,
                },
            )
            assert resp.status_code == 201, resp.text
    return account


async def _forecast(client: AsyncClient, **params: Any) -> dict[str, Any]:
    resp = await client.get(F, params=params)
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def test_forecast_returns_horizon_points_after_history(api_client: AsyncClient) -> None:
    """Covers: KAL-API-019"""
    account = await _account_with_days(api_client, 20)
    body = await _forecast(api_client, account_id=account, horizon_days=30)
    assert (body["account_name"], body["insufficient_data"]) == ("PKO Main", False)
    assert body["forecaster_model"] in {"prophet", "naive"}
    flags = [p["is_forecast"] for p in body["points"]]
    forecast = [p for p in body["points"] if p["is_forecast"]]
    assert len(forecast) == 30
    assert flags == sorted(flags), "history points come first"
    assert flags[0] is False
    dates = [p["date"] for p in body["points"]]
    assert dates == sorted(set(dates)), "dates strictly increase"


async def test_forecast_band_contains_value_and_money_is_decimal_strings(
    api_client: AsyncClient,
) -> None:
    """Covers: KAL-API-019"""
    account = await _account_with_days(api_client, 20)
    body = await _forecast(api_client, account_id=account, horizon_days=30)
    for point in body["points"]:
        assert all(MONEY.match(point[k]) for k in ("value", "lower", "upper")), point
    for point in (p for p in body["points"] if p["is_forecast"]):
        assert float(point["lower"]) <= float(point["value"]) <= float(point["upper"]), point


async def test_kpis_point_at_last_forecast_day(api_client: AsyncClient) -> None:
    """Covers: KAL-API-019"""
    account = await _account_with_days(api_client, 20)
    body = await _forecast(api_client, account_id=account, horizon_days=30)
    last = body["points"][-1]
    assert body["kpis"]["horizon_date"] == last["date"]
    assert body["kpis"]["predicted"] == last["value"]


async def test_conservative_preset_is_not_above_baseline(api_client: AsyncClient) -> None:
    """Covers: KAL-API-019"""
    account = await _account_with_days(api_client, 20)
    base = await _forecast(api_client, account_id=account, horizon_days=30)
    low = await _forecast(api_client, account_id=account, horizon_days=30, preset="conservative")
    assert low["preset"] == "conservative"
    baseline = {p["date"]: float(p["value"]) for p in base["points"] if p["is_forecast"]}
    conservative = {p["date"]: float(p["value"]) for p in low["points"] if p["is_forecast"]}
    assert conservative.keys() == baseline.keys()
    assert all(conservative[d] <= baseline[d] for d in baseline)


async def test_all_accounts_when_account_id_omitted(api_client: AsyncClient) -> None:
    """Covers: KAL-API-019"""
    await _account_with_days(api_client, 20)
    body = await _forecast(api_client, horizon_days=30)
    assert (body["account_name"], body["account_id"]) == ("All Accounts", None)


async def test_insufficient_history_is_200_with_flag(api_client: AsyncClient) -> None:
    """Covers: KAL-API-019"""
    account = await _account_with_days(api_client, 5)
    body = await _forecast(api_client, account_id=account, horizon_days=30)
    assert (body["insufficient_data"], body["points"], body["kpis"]) == (True, [], None)


async def test_unknown_account_is_404(api_client: AsyncClient) -> None:
    """Covers: KAL-API-019"""
    resp = await api_client.get(F, params={"account_id": 999999})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_horizon_out_of_range_is_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-019"""
    zero = await api_client.get(F, params={"horizon_days": 0})
    over = await api_client.get(F, params={"horizon_days": 721})
    assert [zero.status_code, over.status_code] == [422, 422]


async def test_forecast_requires_auth(api_client_unauth: AsyncClient) -> None:
    """Covers: KAL-API-019"""
    assert (await api_client_unauth.get(F)).status_code == 401


async def test_forecast_cache_is_per_family(
    api_client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two families asking for the same account id each get their own forecast run.

    Covers: KAL-API-019
    """
    account = await _account_with_days(api_client, 20)
    runs: list[int] = []

    class CountingForecaster(NaiveForecaster):
        def run(self, running: dict[datetime.date, float], horizon_days: int) -> Any:
            runs.append(horizon_days)
            return super().run(running, horizon_days)

    monkeypatch.setattr(forecast_module, "get_forecaster", CountingForecaster)
    family: list[TenantContext] = [TenantContext(tenant_id=1, schema="t_0123456789ab")]
    monkeypatch.setattr(forecast_module, "current_tenant", lambda: family[0])
    service = ForecastService(session)

    await service.forecast_account(account, 30)
    family[0] = TenantContext(tenant_id=2, schema="t_ba9876543210")
    await service.forecast_account(account, 30)
    assert len(runs) == 2, "the second family is a cache miss"
    family[0] = TenantContext(tenant_id=1, schema="t_0123456789ab")
    await service.forecast_account(account, 30)
    assert len(runs) == 2, "a repeat for the first family is a cache hit"


def test_openapi_lists_forecast_operation_with_summary() -> None:
    """Covers: KAL-API-019"""
    app = FastAPI()
    app.include_router(create_api_router())
    assert app.openapi()["paths"][F]["get"].get("summary")
