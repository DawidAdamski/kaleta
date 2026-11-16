# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/budgets`` realization, range summary, copy-forward and bulk upsert.

Covers: KAL-API-017

Names, amounts and dates are the literals of KAL-API-017.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from kaleta.api import create_api_router
from tests.integration.conftest import (
    budget_payload,
    create_account,
    create_category,
    transaction_payload,
)

B = "/api/v1/budgets"


async def _post_budget(client: AsyncClient, category_id: int, amount: str, month: int) -> None:
    resp = await client.post(
        f"{B}/", json=budget_payload(category_id, amount=amount, month=month, year=2026)
    )
    assert resp.status_code == 201, resp.text


async def _seed(client: AsyncClient) -> dict[str, int]:
    account = (await create_account(client, name="mKonto", balance="0.00"))["id"]
    cats = {
        name: (await create_category(client, name=name, type="expense"))["id"]
        for name in ("Czynsz", "Jedzenie", "Rozrywka", "Prezenty")
    }
    await _post_budget(client, cats["Czynsz"], "2000.00", 4)
    await _post_budget(client, cats["Jedzenie"], "1200.00", 4)
    await _post_budget(client, cats["Rozrywka"], "300.00", 4)
    await _post_budget(client, cats["Jedzenie"], "1000.00", 3)
    for amount, name, date in (
        ("2000.00", "Czynsz", "2026-04-01"),
        ("450.00", "Jedzenie", "2026-04-05"),
        ("360.00", "Rozrywka", "2026-04-10"),
        ("150.00", "Jedzenie", "2026-04-12"),
        ("190.00", "Prezenty", "2026-04-14"),
        ("700.00", "Jedzenie", "2026-03-10"),
        ("999.00", "Jedzenie", "2026-05-02"),
    ):
        resp = await client.post(
            "/api/v1/transactions/",
            json=transaction_payload(account, cats[name], amount=amount, date=date),
        )
        assert resp.status_code == 201, resp.text
    return cats


async def _month(client: AsyncClient, month: int) -> dict[int, str]:
    resp = await client.get(f"{B}/", params={"year": 2026, "month": month})
    return {b["category_id"]: b["amount"] for b in resp.json()}


async def test_realization_for_april_matches_the_scenario(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    await _seed(api_client)
    resp = await api_client.get(
        f"{B}/realization", params={"year": 2026, "month": 4, "as_of": "2026-04-15"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["categories"]
    assert [r["category_name"] for r in rows] == ["Prezenty", "Rozrywka", "Czynsz", "Jedzenie"]
    by: dict[str, dict[str, Any]] = {r["category_name"]: r for r in rows}
    # An unplanned row's planned is the service's Decimal("0"): compared by value.
    prezenty = by["Prezenty"]
    assert (prezenty["status"], Decimal(prezenty["planned"]), prezenty["actual"]) == (
        "over",
        Decimal("0.00"),
        "190.00",
    )
    assert by["Prezenty"]["used_pct"] is None
    assert by["Prezenty"]["pace_delta"] is None
    rozrywka = by["Rozrywka"]
    assert (rozrywka["status"], rozrywka["planned"], rozrywka["actual"]) == (
        "over",
        "300.00",
        "360.00",
    )
    assert (rozrywka["remaining"], rozrywka["used_pct"]) == ("-60.00", 120.0)
    assert (by["Czynsz"]["status"], by["Czynsz"]["actual"], by["Czynsz"]["used_pct"]) == (
        "warning",
        "2000.00",
        100.0,
    )
    jedzenie = by["Jedzenie"]
    assert (jedzenie["status"], jedzenie["actual"], jedzenie["remaining"]) == (
        "on_track",
        "600.00",
        "600.00",
    )
    assert jedzenie["used_pct"] == 50.0
    assert {r["elapsed_pct"] for r in rows} == {50.0}
    assert all(r["note"] is None for r in rows)
    totals = body["totals"]
    assert (totals["planned"], totals["actual"], totals["remaining"]) == (
        "3500.00",
        "3150.00",
        "350.00",
    )
    assert (totals["used_pct"], totals["over"], totals["rows"]) == (90.0, 2, 4)
    assert body["as_of"] == "2026-04-15"


async def test_realization_of_an_empty_month_is_zero_totals(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    resp = await api_client.get(
        f"{B}/realization", params={"year": 2026, "month": 8, "as_of": "2026-08-15"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["categories"] == []
    t = body["totals"]
    assert (t["planned"], t["actual"], t["used_pct"], t["over"], t["rows"]) == (
        "0",
        "0",
        0.0,
        0,
        0,
    )


async def test_realization_rejects_month_13_and_missing_year(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    thirteen = await api_client.get(f"{B}/realization", params={"year": 2026, "month": 13})
    no_year = await api_client.get(f"{B}/realization", params={"month": 4})
    assert [thirteen.status_code, no_year.status_code] == [422, 422]


async def test_summary_march_to_april_matches_the_scenario(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    await _seed(api_client)
    resp = await api_client.get(f"{B}/summary", params={"start": "2026-03-01", "end": "2026-04-30"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [
        (c["category_name"], c["actual_amount"], c["budget_amount"]) for c in body["categories"]
    ] == [
        ("Czynsz", "2000.00", "2000.00"),
        ("Jedzenie", "1300.00", "2200.00"),
        ("Prezenty", "190.00", "0"),
        ("Rozrywka", "360.00", "300.00"),
    ]
    assert (body["budget_total"], body["actual_total"], body["remaining_total"]) == (
        "4500.00",
        "3850.00",
        "650.00",
    )


async def test_summary_end_before_start_is_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    resp = await api_client.get(f"{B}/summary", params={"start": "2026-04-30", "end": "2026-03-01"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_date_range"


async def test_copy_forward_keeps_existing_then_overwrites(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    cats = await _seed(api_client)
    await _post_budget(api_client, cats["Rozrywka"], "250.00", 5)
    copy = {"from_year": 2026, "from_month": 4, "to_year": 2026, "to_month": 5}
    first = await api_client.post(f"{B}/copy-forward", json=copy)
    assert first.status_code == 200, first.text
    assert first.json() == {"written": 2}
    assert await _month(api_client, 5) == {
        cats["Czynsz"]: "2000.00",
        cats["Jedzenie"]: "1200.00",
        cats["Rozrywka"]: "250.00",
    }
    again = await api_client.post(f"{B}/copy-forward", json=copy | {"overwrite": True})
    assert again.json() == {"written": 3}
    assert (await _month(api_client, 5))[cats["Rozrywka"]] == "300.00"


async def test_copy_forward_from_an_empty_month_writes_nothing(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    resp = await api_client.post(
        f"{B}/copy-forward",
        json={"from_year": 2026, "from_month": 9, "to_year": 2026, "to_month": 10},
    )
    assert resp.json() == {"written": 0}


async def test_copy_forward_same_month_is_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    resp = await api_client.post(
        f"{B}/copy-forward",
        json={"from_year": 2026, "from_month": 4, "to_year": 2026, "to_month": 4},
    )
    assert resp.status_code == 422


async def test_bulk_upsert_writes_june(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    cats = await _seed(api_client)
    resp = await api_client.post(
        f"{B}/bulk",
        json={
            "entries": [
                budget_payload(cats["Czynsz"], amount="2000.00", month=6, year=2026),
                budget_payload(cats["Jedzenie"], amount="1100.00", month=6, year=2026),
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"written": 2}
    assert await _month(api_client, 6) == {cats["Czynsz"]: "2000.00", cats["Jedzenie"]: "1100.00"}


async def test_bulk_upsert_unknown_category_is_422_and_writes_nothing(
    api_client: AsyncClient,
) -> None:
    """Covers: KAL-API-017"""
    cats = await _seed(api_client)
    resp = await api_client.post(
        f"{B}/bulk",
        json={
            "entries": [
                budget_payload(cats["Czynsz"], amount="2000.00", month=6, year=2026),
                budget_payload(999999, amount="1100.00", month=6, year=2026),
            ]
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "unknown_category"
    assert await _month(api_client, 6) == {}


async def test_bulk_upsert_empty_entries_is_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-017"""
    resp = await api_client.post(f"{B}/bulk", json={"entries": []})
    assert resp.status_code == 422


def test_openapi_gives_every_new_budget_operation_a_summary() -> None:
    """Covers: KAL-API-017"""
    app = FastAPI()
    app.include_router(create_api_router())
    paths = app.openapi()["paths"]
    ops = [
        paths[f"{B}/realization"]["get"],
        paths[f"{B}/summary"]["get"],
        paths[f"{B}/copy-forward"]["post"],
        paths[f"{B}/bulk"]["post"],
    ]
    assert all(op.get("summary") and op.get("description") for op in ops)
