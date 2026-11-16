# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/reports`` — spending, merchants, budget variance, YTD, YoY, safe to spend.

Covers: KAL-API-016

Names, amounts and dates are the literals of KAL-API-016.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from kaleta.api import create_api_router
from tests.integration.conftest import create_account, create_category

R = "/api/v1/reports"

# date, type, amount, category, payee — the scenario's table.
_ROWS = [
    ("2024-03-10", "expense", "900.00", "Spożywcze", "Lidl"),
    ("2025-02-20", "expense", "150.00", "Paliwo", "Orlen"),
    ("2025-03-01", "income", "6000.00", "Wynagrodzenie", "ACME"),
    ("2025-03-03", "expense", "2000.00", "Czynsz", "Spółdzielnia"),
    ("2025-03-05", "expense", "450.00", "Spożywcze", "Lidl"),
    ("2025-03-12", "expense", "520.00", "Spożywcze", "Biedronka"),
    ("2025-03-14", "expense", "300.00", "Paliwo", "Orlen"),
    ("2025-03-18", "expense", "130.00", "Spożywcze", "Lidl"),
]


def _pct(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value).quantize(Decimal("0.01"))


async def _seed(client: AsyncClient) -> None:
    account = await create_account(client, name="mKonto", balance="0.00", currency="PLN")
    categories = {
        "Wynagrodzenie": (await create_category(client, name="Wynagrodzenie", type="income"))["id"]
    }
    for name in ("Czynsz", "Spożywcze", "Paliwo"):
        categories[name] = (await create_category(client, name=name, type="expense"))["id"]
    for name, amount in (("Czynsz", "2000.00"), ("Spożywcze", "800.00")):
        resp = await client.post(
            "/api/v1/budgets/",
            json={"category_id": categories[name], "amount": amount, "month": 3, "year": 2025},
        )
        assert resp.status_code == 201, resp.text
    for date, kind, amount, category, payee in _ROWS:
        resp = await client.post(
            "/api/v1/transactions/",
            json={
                "account_id": account["id"],
                "category_id": categories[category],
                "amount": amount,
                "type": kind,
                "date": date,
                "payee_name": payee,
            },
        )
        assert resp.status_code == 201, resp.text


async def _get(client: AsyncClient, path: str, **params: Any) -> Any:
    resp = await client.get(f"{R}/{path}", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_reports_scenario(api_client: AsyncClient) -> None:
    """Every literal of the scenario, route by route.

    Covers: KAL-API-016
    """
    await _seed(api_client)

    spending = await _get(api_client, "spending-by-category", start="2025-03-01", end="2025-04-01")
    assert [(r["category"], r["amount"]) for r in spending["rows"]] == [
        ("Czynsz", "2000.00"),
        ("Spożywcze", "1100.00"),
        ("Paliwo", "300.00"),
    ]
    assert spending["total"] == "3400.00"
    assert _pct(spending["rows"][0]["share_pct"]) == Decimal("58.82")

    merchants = await _get(api_client, "top-merchants", start="2025-03-01", end="2025-04-01")
    assert [(m["name"], m["amount"], m["count"]) for m in merchants] == [
        ("Spółdzielnia", "2000.00", 1),
        ("Lidl", "580.00", 2),
        ("Biedronka", "520.00", 1),
        ("Orlen", "300.00", 1),
    ]
    two = await _get(api_client, "top-merchants", start="2025-03-01", end="2025-04-01", limit=2)
    assert [m["name"] for m in two] == ["Spółdzielnia", "Lidl"]

    variance = await _get(api_client, "budget-variance", year=2025, month=3)
    rows = {r["category"]: r for r in variance["rows"]}
    assert [r["category"] for r in variance["rows"]] == ["Czynsz", "Spożywcze", "Paliwo"]
    czynsz, food, fuel = rows["Czynsz"], rows["Spożywcze"], rows["Paliwo"]
    assert (czynsz["planned"], czynsz["actual"], Decimal(czynsz["variance"])) == (
        "2000.00",
        "2000.00",
        Decimal("0"),
    )
    assert czynsz["over_budget"] is False
    assert (food["planned"], food["actual"], food["variance"]) == ("800.00", "1100.00", "-300.00")
    assert _pct(food["spent_pct"]) == Decimal("137.50")
    assert food["over_budget"] is True
    assert (Decimal(fuel["planned"]), fuel["actual"], fuel["variance"]) == (
        Decimal("0"),
        "300.00",
        "-300.00",
    )
    assert fuel["variance_pct"] is None
    assert fuel["over_budget"] is False
    assert (variance["total_planned"], variance["total_actual"]) == ("2800.00", "3400.00")

    ytd = await _get(api_client, "ytd", year=2025)
    assert (ytd["income"], ytd["expenses"], ytd["net"]) == ("6000.00", "3550.00", "2450.00")
    assert _pct(ytd["savings_rate_pct"]) == Decimal("40.83")
    assert [(c["category"], c["amount"]) for c in ytd["top_expense_categories"]] == [
        ("Czynsz", "2000.00"),
        ("Spożywcze", "1100.00"),
        ("Paliwo", "450.00"),
    ]

    yoy = await _get(api_client, "yoy", year=2025, basis="expense")
    assert len(yoy["rows"]) == 12
    march, february = yoy["rows"][2], yoy["rows"][1]
    assert (march["this_year"], march["last_year"], march["delta"]) == (
        "3400.00",
        "900.00",
        "2500.00",
    )
    assert (february["this_year"], Decimal(february["last_year"])) == ("150.00", Decimal("0"))
    assert february["delta_pct"] is None
    assert (yoy["total_this_year"], yoy["total_last_year"], yoy["total_delta"]) == (
        "3550.00",
        "900.00",
        "2650.00",
    )

    safe = await _get(api_client, "safe-to-spend", as_of="2025-03-20")
    assert (safe["income"], safe["spent"], safe["committed"], safe["free"]) == (
        "6000.00",
        "3400.00",
        "0.00",
        "2600.00",
    )
    assert (safe["days_left"], safe["per_day"], safe["trailing_avg_per_day"]) == (
        12,
        "216.67",
        "118.33",
    )
    assert safe["spendable"] is True


async def test_empty_period_is_200_with_zero_totals(api_client: AsyncClient) -> None:
    """Covers: KAL-API-016"""
    spending = await _get(api_client, "spending-by-category", start="2030-01-01", end="2030-02-01")
    assert (spending["rows"], Decimal(spending["total"])) == ([], Decimal("0"))
    assert await _get(api_client, "top-merchants", start="2030-01-01", end="2030-02-01") == []
    variance = await _get(api_client, "budget-variance", year=2030, month=1)
    assert (variance["rows"], Decimal(variance["total_actual"])) == ([], Decimal("0"))
    ytd = await _get(api_client, "ytd", year=2030)
    assert (Decimal(ytd["income"]), ytd["savings_rate_pct"], ytd["top_expense_categories"]) == (
        Decimal("0"),
        None,
        [],
    )
    yoy = await _get(api_client, "yoy", year=2030)
    assert len(yoy["rows"]) == 12
    assert all(r["delta_pct"] is None for r in yoy["rows"])
    safe = await _get(api_client, "safe-to-spend", as_of="2030-01-15")
    assert (Decimal(safe["free"]), safe["spendable"]) == (Decimal("0"), True)


async def test_range_is_checked(api_client: AsyncClient) -> None:
    """Covers: KAL-API-016"""
    for path in ("spending-by-category", "top-merchants"):
        same = await api_client.get(
            f"{R}/{path}", params={"start": "2025-03-01", "end": "2025-03-01"}
        )
        long = await api_client.get(
            f"{R}/{path}", params={"start": "2025-01-01", "end": "2026-01-04"}
        )
        year = await api_client.get(
            f"{R}/{path}", params={"start": "2025-01-01", "end": "2026-01-01"}
        )
        assert [same.status_code, long.status_code, year.status_code] == [422, 422, 200], path
        assert same.json()["error"]["code"] == "validation_error"


async def test_transfer_basis_on_yoy_is_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-016"""
    resp = await api_client.get(f"{R}/yoy", params={"year": 2025, "basis": "transfer"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_top_merchants_limit_bounds(api_client: AsyncClient) -> None:
    """Covers: KAL-API-016"""
    window = {"start": "2025-03-01", "end": "2025-04-01"}
    zero = await api_client.get(f"{R}/top-merchants", params=window | {"limit": 0})
    over = await api_client.get(f"{R}/top-merchants", params=window | {"limit": 101})
    assert [zero.status_code, over.status_code] == [422, 422]


def test_every_new_report_has_a_summary() -> None:
    """Covers: KAL-API-016"""
    app = FastAPI()
    app.include_router(create_api_router())
    paths = app.openapi()["paths"]
    new = (
        "spending-by-category",
        "top-merchants",
        "budget-variance",
        "ytd",
        "yoy",
        "safe-to-spend",
    )
    assert all(paths[f"{R}/{name}"]["get"].get("summary") for name in new)
