# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/subscriptions`` — create, read, update, cancel, reactivate, delete.

Covers: KAL-API-010

Names, amounts and dates are the literals of KAL-API-010.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api import create_api_router
from kaleta.models.category import CategoryType
from kaleta.models.subscription import Subscription
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.payee import PayeeCreate
from kaleta.services import CategoryService
from kaleta.services.payee_service import PayeeService

BASE = "/api/v1/subscriptions"


async def _setup(session: AsyncSession) -> dict[str, int]:
    categories = CategoryService(session)
    await categories.ensure_subscriptions_root_and_children()
    streaming = next(
        c for c in await categories.list_subscription_children() if c.name == "Streaming"
    )
    outside = await categories.create(CategoryCreate(name="Zakupy", type=CategoryType.EXPENSE))
    payee = await PayeeService(session).create(PayeeCreate(name="Amazon"))
    await session.commit()
    return {"streaming": streaming.id, "outside": outside.id, "payee": payee.id}


def _prime(ids: dict[str, int], **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Amazon Prime",
        "amount": "49.00",
        "cadence_days": 365,
        "payee_id": ids["payee"],
        "category_id": ids["streaming"],
        "first_seen_at": "2026-01-10",
    }
    body.update(extra)
    return body


async def test_subscription_round_trip(api_client: AsyncClient, session: AsyncSession) -> None:
    """Create → get → update → cancel → reactivate → delete.

    Covers: KAL-API-010
    """
    ids = await _setup(session)

    created = await api_client.post(f"{BASE}/", json=_prime(ids))
    assert created.status_code == 201, created.text
    sub = created.json()
    assert sub["status"] == "active"
    assert sub["name"] == "Amazon Prime"
    assert sub["amount"] == "49.00"
    assert sub["cadence_days"] == 365
    sub_id = sub["id"]

    got = await api_client.get(f"{BASE}/{sub_id}")
    assert got.status_code == 200
    assert got.json()["category_id"] == ids["streaming"]

    updated = await api_client.put(
        f"{BASE}/{sub_id}",
        json={"notes": "plan roczny", "amount": "59.00", "cadence_days": 30},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["notes"] == "plan roczny"
    assert body["amount"] == "59.00"
    assert body["cadence_days"] == 30
    assert body["name"] == "Amazon Prime"

    cancelled = await api_client.post(f"{BASE}/{sub_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    listed = await api_client.get(f"{BASE}/", params={"status": "cancelled"})
    assert [s["id"] for s in listed.json()] == [sub_id]
    active = await api_client.get(f"{BASE}/", params={"status": "active"})
    assert sub_id not in [s["id"] for s in active.json()]

    reactivated = await api_client.post(f"{BASE}/{sub_id}/reactivate")
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "active"
    assert reactivated.json()["cancelled_at"] is None

    deleted = await api_client.delete(f"{BASE}/{sub_id}")
    assert deleted.status_code == 204
    assert (await api_client.get(f"{BASE}/{sub_id}")).status_code == 404


async def test_notes_are_kept_on_create(api_client: AsyncClient, session: AsyncSession) -> None:
    """A note sent with the POST is stored, not dropped.

    Covers: KAL-API-010
    """
    ids = await _setup(session)
    created = await api_client.post(f"{BASE}/", json=_prime(ids, notes="plan roczny"))
    assert created.status_code == 201
    got = await api_client.get(f"{BASE}/{created.json()['id']}")
    assert got.json()["notes"] == "plan roczny"


async def test_future_cancel_only_schedules(api_client: AsyncClient, session: AsyncSession) -> None:
    """A cancellation dated in the future leaves the subscription active until then.

    Covers: KAL-API-010
    """
    ids = await _setup(session)
    created = await api_client.post(f"{BASE}/", json=_prime(ids, name="BIK"))
    future = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    resp = await api_client.post(
        f"{BASE}/{created.json()['id']}/cancel", params={"effective_on": future}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["cancelled_at"] == future


async def test_category_outside_subscriptions_tree_is_422(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """ADR-028: a subscription files only under the Subscriptions root or its children.

    Covers: KAL-API-010
    """
    ids = await _setup(session)
    bad = await api_client.post(f"{BASE}/", json=_prime(ids, category_id=ids["outside"]))
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "invalid_subscription_category"

    created = await api_client.post(f"{BASE}/", json=_prime(ids))
    resp = await api_client.put(
        f"{BASE}/{created.json()['id']}", json={"category_id": ids["outside"]}
    )
    assert resp.status_code == 422
    unchanged = await api_client.get(f"{BASE}/{created.json()['id']}")
    assert unchanged.json()["category_id"] == ids["streaming"]


async def test_a_legacy_category_does_not_block_other_edits(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A row filed outside the tree before ADR-028 can still have its notes edited.

    Covers: KAL-API-010
    """
    ids = await _setup(session)
    created = await api_client.post(f"{BASE}/", json=_prime(ids))
    sub_id = created.json()["id"]
    legacy = await session.get(Subscription, sub_id)
    if legacy is None:
        raise AssertionError("created subscription not found")
    legacy.category_id = ids["outside"]
    await session.commit()

    resp = await api_client.put(
        f"{BASE}/{sub_id}", json={"notes": "plan roczny", "category_id": ids["outside"]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["notes"] == "plan roczny"


async def test_unknown_payee_is_422(api_client: AsyncClient, session: AsyncSession) -> None:
    """A payee id that does not exist is refused on create and update.

    Covers: KAL-API-010
    """
    ids = await _setup(session)
    bad = await api_client.post(f"{BASE}/", json=_prime(ids, payee_id=999_999))
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "unknown_payee"

    created = await api_client.post(f"{BASE}/", json=_prime(ids))
    resp = await api_client.put(f"{BASE}/{created.json()['id']}", json={"payee_id": 999_999})
    assert resp.status_code == 422


async def test_unknown_id_is_404(api_client: AsyncClient) -> None:
    """Every operation on a missing subscription is 404 in the error envelope.

    Covers: KAL-API-010
    """
    missing = f"{BASE}/999999"
    responses = [
        await api_client.get(missing),
        await api_client.put(missing, json={"notes": "x"}),
        await api_client.delete(missing),
        await api_client.post(f"{missing}/cancel"),
        await api_client.post(f"{missing}/reactivate"),
    ]
    assert [r.status_code for r in responses] == [404] * 5
    assert all(r.json()["error"]["code"] == "not_found" for r in responses)


def test_openapi_gives_every_subscription_operation_a_summary() -> None:
    """The API docs list each subscription operation with a summary.

    Covers: KAL-API-010
    """
    app = FastAPI()
    app.include_router(create_api_router())
    paths = app.openapi()["paths"]
    operations = {
        (method.upper(), path): op
        for path, item in paths.items()
        if path.startswith(BASE)
        for method, op in item.items()
    }
    expected = {
        ("GET", f"{BASE}/"),
        ("POST", f"{BASE}/"),
        ("GET", f"{BASE}/{{sub_id}}"),
        ("PUT", f"{BASE}/{{sub_id}}"),
        ("DELETE", f"{BASE}/{{sub_id}}"),
        ("POST", f"{BASE}/{{sub_id}}/cancel"),
        ("POST", f"{BASE}/{{sub_id}}/reactivate"),
    }
    assert expected <= operations.keys()
    assert all(operations[key].get("summary") for key in expected)
