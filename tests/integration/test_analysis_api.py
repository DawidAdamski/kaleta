# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only analysis API endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_list_subscriptions_empty(api_client) -> None:
    resp = await api_client.get("/api/v1/subscriptions/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_personal_loans_empty(api_client) -> None:
    resp = await api_client.get("/api/v1/personal-loans/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_reserve_funds_empty(api_client) -> None:
    resp = await api_client.get("/api/v1/reserve-funds/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_net_worth_snapshot(api_client) -> None:
    created = await api_client.post(
        "/api/v1/accounts/",
        json={
            "name": "Cash",
            "type": "checking",
            "balance": "250.00",
            "currency": "PLN",
        },
    )
    assert created.status_code == 201
    resp = await api_client.get("/api/v1/net-worth/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_currency"] == "PLN"
    assert Decimal(body["net_worth"]) == Decimal("250.00")


@pytest.mark.asyncio
async def test_reports_cashflow(api_client) -> None:
    resp = await api_client.get("/api/v1/reports/cashflow", params={"months": 3})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_reports_income_statement(api_client) -> None:
    today = date.today()
    resp = await api_client.get(
        "/api/v1/reports/income-statement",
        params={"year": today.year, "month": today.month},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == today.year
    assert body["month"] == today.month
    assert "total_income" in body
    assert "total_expenses" in body
