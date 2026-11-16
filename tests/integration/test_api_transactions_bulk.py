# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/transactions`` bulk routes, new transfers and the ledger CSV.

Covers: KAL-API-014

Names, amounts and dates are the literals of KAL-API-014.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from kaleta.api import create_api_router
from kaleta.config import settings
from tests.integration.conftest import create_account, create_category

TX = "/api/v1/transactions"


async def _world(client: AsyncClient) -> dict[str, int]:
    mkonto = await create_account(client, name="mKonto", balance="0.00", currency="PLN")
    savings = await create_account(client, name="Savings", balance="0.00", currency="PLN")
    eur = await create_account(client, name="Revolut EUR", balance="0.00", currency="EUR")
    food = await create_category(client, name="Spożywcze", type="expense")
    transport = await create_category(client, name="Transport", type="expense")
    salary = await create_category(client, name="Wynagrodzenie", type="income")
    return {
        "mkonto": mkonto["id"],
        "savings": savings["id"],
        "eur": eur["id"],
        "food": food["id"],
        "transport": transport["id"],
        "salary": salary["id"],
    }


def _rows(w: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "account_id": w["mkonto"],
            "category_id": w["food"],
            "amount": "45.99",
            "type": "expense",
            "date": "2026-11-03",
            "description": "LIDL WARSZAWA",
        },
        {
            "account_id": w["mkonto"],
            "category_id": w["food"],
            "amount": "120.00",
            "type": "expense",
            "date": "2026-11-04",
            "description": "ORLEN",
        },
    ]


async def _count(client: AsyncClient) -> int:
    total: int = (await client.get(f"{TX}/")).json()["total"]
    return total


async def _bulk(client: AsyncClient, w: dict[str, int]) -> list[int]:
    resp = await client.post(f"{TX}/bulk", json={"transactions": _rows(w)})
    assert resp.status_code == 201, resp.text
    ids: list[int] = resp.json()["ids"]
    return ids


async def _categories(client: AsyncClient, ids: list[int]) -> list[int]:
    return [(await client.get(f"{TX}/{i}")).json()["category_id"] for i in ids]


async def test_bulk_create_stores_both_rows_and_returns_ids(api_client: AsyncClient) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    resp = await api_client.post(f"{TX}/bulk", json={"transactions": _rows(w)})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created_count"] == 2
    got = [(await api_client.get(f"{TX}/{i}")).json() for i in body["ids"]]
    assert [(g["amount"], g["account_id"]) for g in got] == [
        ("45.99", w["mkonto"]),
        ("120.00", w["mkonto"]),
    ]


async def test_bulk_create_unknown_account_stores_nothing(api_client: AsyncClient) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    rows = _rows(w)
    rows[1]["account_id"] = 999999
    resp = await api_client.post(f"{TX}/bulk", json={"transactions": rows})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "unknown_account"
    assert await _count(api_client) == 0


async def test_bulk_create_refuses_splits_tags_and_transfer_rows(api_client: AsyncClient) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    first = _rows(w)[0]
    split = first | {
        "category_id": None,
        "is_split": True,
        "splits": [{"category_id": w["food"], "amount": "45.99"}],
    }
    tagged = first | {"tag_ids": [1]}
    transfer = first | {"category_id": None, "type": "transfer", "transfer_direction": "out"}
    for row in (split, tagged, transfer):
        resp = await api_client.post(f"{TX}/bulk", json={"transactions": [row]})
        assert resp.status_code == 422, (row, resp.text)
        assert resp.json()["error"]["code"] == "unsupported_in_bulk"
    assert await _count(api_client) == 0


async def test_bulk_category_moves_both_rows(api_client: AsyncClient) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    ids = await _bulk(api_client, w)
    resp = await api_client.post(
        f"{TX}/bulk/category", json={"transaction_ids": ids, "category_id": w["transport"]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated_count": 2}
    assert await _categories(api_client, ids) == [w["transport"], w["transport"]]


async def test_bulk_category_wrong_type_changes_nothing(api_client: AsyncClient) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    ids = await _bulk(api_client, w)
    resp = await api_client.post(
        f"{TX}/bulk/category", json={"transaction_ids": ids, "category_id": w["salary"]}
    )
    assert resp.status_code == 422
    assert await _categories(api_client, ids) == [w["food"], w["food"]]


async def test_bulk_category_unknown_id_is_404_and_changes_nothing(
    api_client: AsyncClient,
) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    ids = await _bulk(api_client, w)
    resp = await api_client.post(
        f"{TX}/bulk/category",
        json={"transaction_ids": [*ids, 999999], "category_id": w["transport"]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    assert await _categories(api_client, ids) == [w["food"], w["food"]]


async def test_bulk_over_cap_is_413(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    ids = await _bulk(api_client, w)
    monkeypatch.setattr(settings, "api_bulk_max_items", 1)
    rows = await api_client.post(f"{TX}/bulk", json={"transactions": _rows(w)})
    cats = await api_client.post(
        f"{TX}/bulk/category", json={"transaction_ids": ids, "category_id": w["transport"]}
    )
    assert [rows.status_code, cats.status_code] == [413, 413]
    assert await _count(api_client) == 2
    assert await _categories(api_client, ids) == [w["food"], w["food"]]


async def test_transfer_creates_two_linked_legs(api_client: AsyncClient) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    resp = await api_client.post(
        f"{TX}/transfers",
        json={
            "from_account_id": w["mkonto"],
            "to_account_id": w["savings"],
            "amount": "500.00",
            "date": "2026-11-05",
            "description": "Na oszczędności",
        },
    )
    assert resp.status_code == 201, resp.text
    out, inc = resp.json()["outgoing"], resp.json()["incoming"]
    assert (out["account_id"], inc["account_id"]) == (w["mkonto"], w["savings"])
    assert (out["amount"], inc["amount"]) == ("500.00", "500.00")
    assert {out["type"], inc["type"]} == {"transfer"}
    assert out["is_internal_transfer"] and inc["is_internal_transfer"]
    assert (out["transfer_direction"], inc["transfer_direction"]) == ("out", "in")
    assert (out["linked_transaction_id"], inc["linked_transaction_id"]) == (inc["id"], out["id"])
    assert (out["category_id"], inc["category_id"]) == (None, None)


async def test_transfer_same_account_is_422_unknown_account_404(api_client: AsyncClient) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    base = {"amount": "500.00", "date": "2026-11-05"}
    same = await api_client.post(
        f"{TX}/transfers",
        json=base | {"from_account_id": w["mkonto"], "to_account_id": w["mkonto"]},
    )
    unknown = await api_client.post(
        f"{TX}/transfers",
        json=base | {"from_account_id": w["mkonto"], "to_account_id": 999999},
    )
    assert [same.status_code, unknown.status_code] == [422, 404]
    assert await _count(api_client) == 0


async def test_cross_currency_transfer_needs_rate_and_rounds_incoming_leg(
    api_client: AsyncClient,
) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    base = {"from_account_id": w["mkonto"], "to_account_id": w["eur"], "date": "2026-11-05"}
    no_rate = await api_client.post(f"{TX}/transfers", json=base | {"amount": "460.00"})
    assert no_rate.status_code == 422
    resp = await api_client.post(
        f"{TX}/transfers", json=base | {"amount": "460.00", "exchange_rate": "0.2350"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["outgoing"]["amount"] == "460.00"
    assert resp.json()["incoming"]["amount"] == "108.10"


async def test_export_is_csv_attachment_with_scenario_row(api_client: AsyncClient) -> None:
    """Covers: KAL-API-014"""
    w = await _world(api_client)
    ids = await _bulk(api_client, w)
    await api_client.post(
        f"{TX}/bulk/category", json={"transaction_ids": ids, "category_id": w["transport"]}
    )
    resp = await api_client.get(f"{TX}/export")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    disposition = resp.headers["content-disposition"]
    assert re.fullmatch(r'attachment; filename="kaleta_ledger_\d{4}-\d{2}-\d{2}\.csv"', disposition)
    lines = resp.text.splitlines()
    assert lines[0] == (
        "date,type,amount,currency,account,category,payee,description,tags,is_internal_transfer"
    )
    assert "2026-11-03,expense,45.99,PLN,mKonto,Transport,,LIDL WARSZAWA,,false" in lines


def test_openapi_gives_every_bulk_operation_a_summary() -> None:
    """Covers: KAL-API-014"""
    app = FastAPI()
    app.include_router(create_api_router())
    paths = app.openapi()["paths"]
    ops = [
        paths[f"{TX}/bulk"]["post"],
        paths[f"{TX}/bulk/category"]["post"],
        paths[f"{TX}/transfers"]["post"],
        paths[f"{TX}/export"]["get"],
    ]
    assert all(op.get("summary") and op.get("description") for op in ops)
