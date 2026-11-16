# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/reserve-funds`` — create, edit, archive, delete funds; run a savings goal.

Covers: KAL-API-013

Names, amounts and dates are the literals of KAL-API-013.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from kaleta.api import create_api_router
from tests.integration.conftest import create_account, create_category

BASE = "/api/v1/reserve-funds"


async def _accounts(client: AsyncClient) -> dict[str, int]:
    main = await create_account(client, name="PKO Main", balance="1000.00", currency="PLN")
    goal = await create_account(client, name="Konto wakacyjne", balance="0.00", currency="PLN")
    eur = await create_account(client, name="Konto EUR", balance="0.00", currency="EUR")
    return {"main": main["id"], "goal": goal["id"], "eur": eur["id"]}


async def _balance(client: AsyncClient, account_id: int) -> str:
    resp = await client.get(f"/api/v1/accounts/{account_id}")
    assert resp.status_code == 200, resp.text
    balance: str = resp.json()["balance"]
    return balance


async def _goal(client: AsyncClient, backing_account_id: int) -> dict[str, Any]:
    resp = await client.post(
        f"{BASE}/",
        json={
            "name": "Wakacje 2030",
            "kind": "vacation",
            "target_amount": "6000.00",
            "target_date": "2030-06-01",
            "backing_account_id": backing_account_id,
        },
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def _emergency(client: AsyncClient, backing_account_id: int) -> int:
    resp = await client.post(
        f"{BASE}/",
        json={
            "name": "Poduszka",
            "kind": "emergency",
            "target_amount": "10000.00",
            "backing_account_id": backing_account_id,
        },
    )
    assert resp.status_code == 201, resp.text
    fund_id: int = resp.json()["id"]
    return fund_id


async def test_goal_round_trip_through_the_api(api_client: AsyncClient) -> None:
    """Create → get → contribute → put → close with release → list → unarchive → delete.

    Covers: KAL-API-013
    """
    acc = await _accounts(api_client)
    goal = await _goal(api_client, acc["goal"])
    assert goal["is_archived"] is False
    fund = f"{BASE}/{goal['id']}"

    fetched = (await api_client.get(fund)).json()
    assert (fetched["current_balance"], fetched["progress_pct"]) == ("0.00", "0.00")
    assert fetched["months_left"] > 0
    assert fetched["monthly_pace"] is not None

    contributed = await api_client.post(
        f"{fund}/contribute",
        json={"amount": "500.00", "from_account_id": acc["main"], "date": "2026-11-15"},
    )
    assert contributed.status_code == 200, contributed.text
    body = contributed.json()
    assert (body["current_balance"], body["progress_pct"]) == ("500.00", "0.08")
    assert await _balance(api_client, acc["main"]) == "500.00"

    edited = await api_client.put(
        fund, json={"name": "Wakacje w Grecji 2030", "target_amount": "5000.00"}
    )
    assert edited.status_code == 200, edited.text
    assert (edited.json()["name"], edited.json()["target_amount"]) == (
        "Wakacje w Grecji 2030",
        "5000.00",
    )
    assert (await api_client.get(fund)).json()["progress_pct"] == "0.10"

    closed = await api_client.post(
        f"{fund}/close", json={"release_to_account_id": acc["main"], "date": "2026-11-20"}
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["is_archived"] is True
    assert await _balance(api_client, acc["main"]) == "1000.00"
    assert await _balance(api_client, acc["goal"]) == "0.00"

    live = (await api_client.get(f"{BASE}/")).json()
    every = (await api_client.get(f"{BASE}/", params={"include_archived": "true"})).json()
    assert goal["id"] not in [f["id"] for f in live]
    assert goal["id"] in [f["id"] for f in every]

    reopened = await api_client.post(f"{fund}/unarchive")
    assert reopened.status_code == 200
    assert (reopened.json()["is_archived"], reopened.json()["archived_at"]) == (False, None)

    assert (await api_client.delete(fund)).status_code == 204
    assert (await api_client.get(fund)).status_code == 404


async def test_contribute_refuses_currency_mismatch_self_transfer_and_non_goal(
    api_client: AsyncClient,
) -> None:
    """Another currency, the backing account itself, a non-goal and a closed goal are 422.

    Covers: KAL-API-013
    """
    acc = await _accounts(api_client)
    goal_id = (await _goal(api_client, acc["goal"]))["id"]
    emergency_id = await _emergency(api_client, acc["main"])

    def contribution(from_id: int) -> dict[str, Any]:
        return {"amount": "500.00", "from_account_id": from_id, "date": "2026-11-15"}

    eur = await api_client.post(f"{BASE}/{goal_id}/contribute", json=contribution(acc["eur"]))
    itself = await api_client.post(f"{BASE}/{goal_id}/contribute", json=contribution(acc["goal"]))
    non_goal = await api_client.post(
        f"{BASE}/{emergency_id}/contribute", json=contribution(acc["goal"])
    )
    assert [eur.status_code, itself.status_code, non_goal.status_code] == [422, 422, 422]

    await api_client.post(f"{BASE}/{goal_id}/close", json={"date": "2026-11-20"})
    after_close = await api_client.post(
        f"{BASE}/{goal_id}/contribute", json=contribution(acc["main"])
    )
    assert after_close.status_code == 422
    assert await _balance(api_client, acc["main"]) == "1000.00"


async def test_close_without_release_moves_no_money(api_client: AsyncClient) -> None:
    """Closing without a release account archives the goal and leaves its balance.

    Covers: KAL-API-013
    """
    acc = await _accounts(api_client)
    goal_id = (await _goal(api_client, acc["goal"]))["id"]
    await api_client.post(
        f"{BASE}/{goal_id}/contribute",
        json={"amount": "500.00", "from_account_id": acc["main"], "date": "2026-11-15"},
    )
    closed = await api_client.post(f"{BASE}/{goal_id}/close", json={"date": "2026-11-20"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["is_archived"] is True
    assert await _balance(api_client, acc["goal"]) == "500.00"
    assert await _balance(api_client, acc["main"]) == "500.00"


async def test_unknown_fund_is_404_on_every_route(api_client: AsyncClient) -> None:
    """Every fund route on id 999999 is 404.

    Covers: KAL-API-013
    """
    missing = f"{BASE}/999999"
    acc = await create_account(api_client, name="PKO Main", balance="1000.00")
    responses = [
        await api_client.get(missing),
        await api_client.put(missing, json={"name": "x"}),
        await api_client.delete(missing),
        await api_client.post(f"{missing}/archive"),
        await api_client.post(f"{missing}/unarchive"),
        await api_client.post(
            f"{missing}/contribute",
            json={"amount": "1.00", "from_account_id": acc["id"], "date": "2026-11-15"},
        ),
        await api_client.post(f"{missing}/close", json={"date": "2026-11-20"}),
    ]
    assert [r.status_code for r in responses] == [404] * 7
    assert all(r.json()["error"]["code"] == "not_found" for r in responses)


async def test_unknown_backing_account_is_422(api_client: AsyncClient) -> None:
    """A backing account that does not exist is refused on create and on update.

    Covers: KAL-API-013
    """
    acc = await _accounts(api_client)
    created = await api_client.post(
        f"{BASE}/",
        json={
            "name": "Wakacje 2030",
            "kind": "vacation",
            "target_amount": "6000.00",
            "backing_account_id": 999999,
        },
    )
    assert created.status_code == 422, created.text
    assert created.json()["error"]["code"] == "unknown_backing_account"
    assert (await api_client.get(f"{BASE}/")).json() == []

    goal_id = (await _goal(api_client, acc["goal"]))["id"]
    moved = await api_client.put(f"{BASE}/{goal_id}", json={"backing_account_id": 999999})
    assert moved.status_code == 422
    assert moved.json()["error"]["code"] == "unknown_backing_account"
    assert (await api_client.get(f"{BASE}/{goal_id}")).json()["backing_account_id"] == acc["goal"]


async def test_envelope_fund_needs_an_existing_category(api_client: AsyncClient) -> None:
    """An envelope fund backed by an unknown category is 422; by a real one, 201.

    Covers: KAL-API-013
    """
    category = await create_category(api_client, name="Wakacje")

    def envelope(category_id: int) -> dict[str, Any]:
        return {
            "name": "Wakacje 2030",
            "kind": "vacation",
            "target_amount": "6000.00",
            "backing_mode": "envelope",
            "backing_category_id": category_id,
        }

    unknown = await api_client.post(f"{BASE}/", json=envelope(999999))
    assert unknown.status_code == 422, unknown.text
    assert unknown.json()["error"]["code"] == "unknown_backing_category"

    created = await api_client.post(f"{BASE}/", json=envelope(category["id"]))
    assert created.status_code == 201, created.text
    fund_id = created.json()["id"]
    moved = await api_client.put(f"{BASE}/{fund_id}", json={"backing_category_id": 999999})
    assert moved.status_code == 422
    assert moved.json()["error"]["code"] == "unknown_backing_category"
    got = (await api_client.get(f"{BASE}/{fund_id}")).json()
    assert (got["backing_category_id"], got["current_balance"]) == (category["id"], "0.00")


async def test_put_cannot_null_a_required_field_or_date_a_non_goal(
    api_client: AsyncClient,
) -> None:
    """A null name, a target_date on an emergency fund, a bare backing_mode switch: 422.

    Covers: KAL-API-013
    """
    acc = await _accounts(api_client)
    emergency_id = await _emergency(api_client, acc["main"])
    fund = f"{BASE}/{emergency_id}"
    bodies = [{"name": None}, {"target_date": "2030-06-01"}, {"backing_mode": "envelope"}]
    for body in bodies:
        resp = await api_client.put(fund, json=body)
        assert resp.status_code == 422, (body, resp.text)
        assert resp.json()["error"]["code"] == "invalid_reserve_fund"

    after = await api_client.get(fund)
    assert after.status_code == 200
    got = after.json()
    assert (got["name"], got["target_date"], got["backing_mode"]) == ("Poduszka", None, "account")
    assert (await api_client.get(f"{BASE}/")).status_code == 200


async def test_put_kind_change_drops_the_date(api_client: AsyncClient) -> None:
    """A goal turned into an emergency fund loses its target_date, as in the UI.

    Covers: KAL-API-013
    """
    acc = await _accounts(api_client)
    goal_id = (await _goal(api_client, acc["goal"]))["id"]
    resp = await api_client.put(
        f"{BASE}/{goal_id}", json={"kind": "emergency", "emergency_multiplier": 3}
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["kind"], resp.json()["target_date"]) == ("emergency", None)


def test_openapi_gives_every_reserve_fund_operation_a_summary() -> None:
    """Every operation under /api/v1/reserve-funds has a summary.

    Covers: KAL-API-013
    """
    app = FastAPI()
    app.include_router(create_api_router())
    ops = [
        (path, method, op)
        for path, item in app.openapi()["paths"].items()
        if path.startswith(BASE)
        for method, op in item.items()
    ]
    # list, create, get, put, delete, archive, unarchive, contribute, close + 5 item routes
    assert len(ops) == 14
    assert all(op.get("summary") for _, _, op in ops)
