# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/tags`` and ``/api/v1/categorisation-rules``.

Covers: KAL-API-015

Names, amounts and dates are the literals of KAL-API-015.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api import create_api_router
from kaleta.models.tag import transaction_tags
from tests.integration.conftest import create_account, create_category

TAGS = "/api/v1/tags"
RULES = "/api/v1/categorisation-rules"


async def _tag(client: AsyncClient, name: str = "Wakacje") -> dict[str, Any]:
    resp = await client.post(f"{TAGS}/", json={"name": name, "color": "#2E7D32"})
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def _world(client: AsyncClient) -> dict[str, int]:
    account = await create_account(client, name="mKonto", balance="0.00")
    food = await create_category(client, name="Spożywcze", type="expense")
    alcohol = await create_category(client, name="Alkohol", type="expense")
    return {"account": account["id"], "food": food["id"], "alcohol": alcohol["id"]}


async def _rule(client: AsyncClient, category_id: int) -> dict[str, Any]:
    resp = await client.post(
        f"{RULES}/", json={"pattern": "LIDL", "category_id": category_id, "priority": 10}
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


# ── Tags ──────────────────────────────────────────────────────────────────────


async def test_tag_crud_round_trip(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    tag = await _tag(api_client)
    assert [t["name"] for t in (await api_client.get(f"{TAGS}/")).json()] == ["Wakacje"]
    renamed = await api_client.put(f"{TAGS}/{tag['id']}", json={"name": "Urlop 2026"})
    assert renamed.status_code == 200, renamed.text
    got = (await api_client.get(f"{TAGS}/{tag['id']}")).json()
    assert (got["name"], got["color"]) == ("Urlop 2026", "#2E7D32")


async def test_duplicate_tag_name_is_409(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    first = await _tag(api_client)
    again = await api_client.post(f"{TAGS}/", json={"name": "Wakacje"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "conflict"
    other = await _tag(api_client, "Urlop 2026")
    rename = await api_client.put(f"{TAGS}/{other['id']}", json={"name": "Wakacje"})
    assert rename.status_code == 409
    keep = await api_client.put(f"{TAGS}/{first['id']}", json={"name": "Wakacje"})
    assert keep.status_code == 200


async def test_blank_tag_name_is_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    resp = await api_client.post(f"{TAGS}/", json={"name": "   "})
    assert resp.status_code == 422
    assert (await api_client.get(f"{TAGS}/")).json() == []


async def test_null_tag_name_on_update_is_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    tag = await _tag(api_client)
    resp = await api_client.put(f"{TAGS}/{tag['id']}", json={"name": None})
    assert resp.status_code == 422
    assert (await api_client.get(f"{TAGS}/{tag['id']}")).json()["name"] == "Wakacje"
    cleared = await api_client.put(f"{TAGS}/{tag['id']}", json={"color": None})
    assert cleared.status_code == 200
    assert cleared.json()["color"] is None


async def test_tag_404s(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    missing = f"{TAGS}/999999"
    responses = [
        await api_client.get(missing),
        await api_client.put(missing, json={"name": "x"}),
        await api_client.delete(missing),
    ]
    assert [r.status_code for r in responses] == [404] * 3


async def test_deleting_a_tag_keeps_its_transactions(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    tag = await _tag(api_client, "Urlop 2026")
    tx = await api_client.post(
        "/api/v1/transactions/",
        json={
            "account_id": w["account"],
            "category_id": w["food"],
            "amount": "54.30",
            "type": "expense",
            "date": "2026-11-14",
            "description": "Hotel Sopot",
            "tag_ids": [tag["id"]],
        },
    )
    assert tx.status_code == 201, tx.text
    tx_id = tx.json()["id"]

    async def links() -> int:
        stmt = select(func.count()).where(transaction_tags.c.transaction_id == tx_id)
        count: int = (await session.execute(stmt)).scalar_one()
        return count

    assert await links() == 1
    assert (await api_client.delete(f"{TAGS}/{tag['id']}")).status_code == 204
    assert (await api_client.get(f"{TAGS}/")).json() == []
    still = await api_client.get(f"/api/v1/transactions/{tx_id}")
    assert still.status_code == 200
    assert (still.json()["amount"], still.json()["description"]) == ("54.30", "Hotel Sopot")
    assert await links() == 0


# ── Categorisation rules ─────────────────────────────────────────────────────


async def test_rule_crud_round_trip(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    rule = await _rule(api_client, w["food"])
    assert (rule["category_name"], rule["match_mode"], rule["is_active"], rule["priority"]) == (
        "Spożywcze",
        "contains",
        True,
        10,
    )
    got = await api_client.get(f"{RULES}/{rule['id']}")
    assert got.json()["pattern"] == "LIDL"
    assert [r["id"] for r in (await api_client.get(f"{RULES}/")).json()] == [rule["id"]]
    assert (await api_client.delete(f"{RULES}/{rule['id']}")).status_code == 204
    assert (await api_client.get(f"{RULES}/{rule['id']}")).status_code == 404


async def test_rule_unknown_category_is_404(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    resp = await api_client.post(f"{RULES}/", json={"pattern": "LIDL", "category_id": 999999})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    assert (await api_client.get(f"{RULES}/")).json() == []


async def test_blank_rule_pattern_is_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    resp = await api_client.post(f"{RULES}/", json={"pattern": "   ", "category_id": w["food"]})
    assert resp.status_code == 422


async def test_update_rule_category_returns_new_category_name(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    rule = await _rule(api_client, w["food"])
    resp = await api_client.put(
        f"{RULES}/{rule['id']}", json={"category_id": w["alcohol"], "is_active": False}
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["category_name"], resp.json()["is_active"]) == ("Alkohol", False)


async def test_active_only_filter_hides_inactive_rule(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    rule = await _rule(api_client, w["food"])
    await api_client.put(f"{RULES}/{rule['id']}", json={"is_active": False})
    active = await api_client.get(f"{RULES}/", params={"active_only": "true"})
    every = await api_client.get(f"{RULES}/")
    assert active.json() == []
    assert [r["id"] for r in every.json()] == [rule["id"]]


async def test_null_fields_on_rule_update_are_422(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    rule = await _rule(api_client, w["food"])
    for field in ("category_id", "match_mode", "is_active", "priority"):
        resp = await api_client.put(f"{RULES}/{rule['id']}", json={field: None})
        assert resp.status_code == 422, (field, resp.text)
    got = (await api_client.get(f"{RULES}/{rule['id']}")).json()
    assert (got["category_id"], got["is_active"], got["priority"]) == (w["food"], True, 10)


async def test_rule_delete_twice_is_404(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    rule = await _rule(api_client, w["food"])
    first = await api_client.delete(f"{RULES}/{rule['id']}")
    second = await api_client.delete(f"{RULES}/{rule['id']}")
    assert [first.status_code, second.status_code] == [204, 404]


# ── Suggestions ───────────────────────────────────────────────────────────────


async def _lidl_expenses(client: AsyncClient, w: dict[str, int], count: int) -> None:
    for _ in range(count):
        resp = await client.post(
            "/api/v1/transactions/",
            json={
                "account_id": w["account"],
                "category_id": w["food"],
                "amount": "54.30",
                "type": "expense",
                "date": "2026-11-14",
                "description": "LIDL WARSZAWA",
            },
        )
        assert resp.status_code == 201, resp.text


async def test_suggestion_after_four_categorisations(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    await _lidl_expenses(api_client, w, 4)
    resp = await api_client.post(
        f"{RULES}/suggestions", json={"description": "LIDL WARSZAWA", "category_id": w["food"]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["pattern"], body["category_name"], body["match_count"]) == (
        "LIDL WARSZAWA",
        "Spożywcze",
        4,
    )
    assert (await api_client.get(f"{RULES}/")).json() == []


async def test_no_suggestion_below_threshold(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    await _lidl_expenses(api_client, w, 3)
    resp = await api_client.post(
        f"{RULES}/suggestions", json={"description": "LIDL WARSZAWA", "category_id": w["food"]}
    )
    assert resp.status_code == 200
    assert resp.json() is None


async def test_rules_api_does_not_touch_import_rules(api_client: AsyncClient) -> None:
    """Covers: KAL-API-015"""
    w = await _world(api_client)
    await _rule(api_client, w["food"])
    assert (await api_client.get("/api/v1/import-rules/")).json() == []


def test_openapi_gives_every_rule_and_tag_operation_a_summary() -> None:
    """Covers: KAL-API-015"""
    app = FastAPI()
    app.include_router(create_api_router())
    ops = [
        op
        for path, item in app.openapi()["paths"].items()
        if path.startswith((TAGS, RULES))
        for op in item.values()
    ]
    assert len(ops) == 11
    assert all(op.get("summary") for op in ops)
