# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/planned-transactions`` — standing orders and other plans.

Covers: KAL-API-012

Names, amounts and dates are the literals of KAL-API-012.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api import create_api_router
from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.services import AccountService

BASE = "/api/v1/planned-transactions"


async def _accounts(session: AsyncSession) -> tuple[int, int]:
    service = AccountService(session)
    main = await service.create(
        AccountCreate(name="mKonto", type=AccountType.CHECKING, balance=Decimal("0.00"))
    )
    savings = await service.create(
        AccountCreate(name="Oszczędności", type=AccountType.SAVINGS, balance=Decimal("0.00"))
    )
    await session.commit()
    return main.id, savings.id


def _standing_order(account_id: int, target_id: int) -> dict[str, object]:
    return {
        "name": "Przelew na oszczędności",
        "amount": "2049.07",
        "type": "transfer",
        "account_id": account_id,
        "target_account_id": target_id,
        "frequency": "monthly",
        "start_date": "2026-01-10",
    }


async def test_standing_order_round_trip(api_client: AsyncClient, session: AsyncSession) -> None:
    """Create a self-transfer → get → occurrences → raise the amount → pause → delete.

    Covers: KAL-API-012
    """
    main_id, savings_id = await _accounts(session)

    created = await api_client.post(f"{BASE}/", json=_standing_order(main_id, savings_id))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["is_active"] is True
    assert body["target_account_id"] == savings_id
    assert body["account_id"] == main_id
    pt_id = body["id"]

    fetched = await api_client.get(f"{BASE}/{pt_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Przelew na oszczędności"

    window = {"start": "2026-01-01", "end": "2026-03-31"}
    occ = await api_client.get(f"{BASE}/{pt_id}/occurrences", params=window)
    assert occ.status_code == 200, occ.text
    assert [(o["date"], o["amount"]) for o in occ.json()] == [
        ("2026-01-10", "2049.07"),
        ("2026-02-10", "2049.07"),
        ("2026-03-10", "2049.07"),
    ]

    raised = await api_client.put(f"{BASE}/{pt_id}", json={"amount": "5378.00"})
    assert raised.status_code == 200, raised.text
    assert raised.json()["amount"] == "5378.00"
    assert raised.json()["name"] == "Przelew na oszczędności"
    occ = await api_client.get(f"{BASE}/{pt_id}/occurrences", params=window)
    assert {o["amount"] for o in occ.json()} == {"5378.00"}

    paused = await api_client.post(f"{BASE}/{pt_id}/toggle-active")
    assert paused.status_code == 200
    assert paused.json()["is_active"] is False
    inactive = await api_client.get(f"{BASE}/", params={"active": "false"})
    active = await api_client.get(f"{BASE}/", params={"active": "true"})
    assert [p["id"] for p in inactive.json()] == [pt_id]
    assert active.json() == []

    deleted = await api_client.delete(f"{BASE}/{pt_id}")
    assert deleted.status_code == 204
    assert (await api_client.get(f"{BASE}/{pt_id}")).status_code == 404


async def test_unknown_references_are_422(api_client: AsyncClient, session: AsyncSession) -> None:
    """An account, target account, category or payee that does not exist is refused.

    Covers: KAL-API-012
    """
    main_id, savings_id = await _accounts(session)
    cases = {
        "unknown_account": {"account_id": 999999},
        "unknown_category": {"category_id": 999999},
        "unknown_payee": {"payee_id": 999999},
    }
    for code, override in cases.items():
        r = await api_client.post(f"{BASE}/", json=_standing_order(main_id, savings_id) | override)
        assert r.status_code == 422, (code, r.text)
        assert r.json()["error"]["code"] == code
    target = await api_client.post(
        f"{BASE}/", json=_standing_order(main_id, savings_id) | {"target_account_id": 999999}
    )
    assert target.status_code == 422
    assert target.json()["error"]["code"] == "unknown_account"
    assert (await api_client.get(f"{BASE}/")).json() == []


async def test_put_null_required_field_is_422(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A partial update may leave a required field out, but not set it to null.

    Covers: KAL-API-012
    """
    main_id, savings_id = await _accounts(session)
    pt_id = (await api_client.post(f"{BASE}/", json=_standing_order(main_id, savings_id))).json()[
        "id"
    ]
    for field in ("name", "amount", "account_id", "start_date"):
        r = await api_client.put(f"{BASE}/{pt_id}", json={field: None})
        assert r.status_code == 422, (field, r.text)
        assert r.json()["error"]["code"] == "null_field"
    unknown = await api_client.put(f"{BASE}/{pt_id}", json={"account_id": 999999})
    assert unknown.status_code == 422
    still = (await api_client.get(f"{BASE}/{pt_id}")).json()
    assert (still["name"], still["amount"], still["account_id"]) == (
        "Przelew na oszczędności",
        "2049.07",
        main_id,
    )


async def test_occurrence_window_is_checked(api_client: AsyncClient, session: AsyncSession) -> None:
    """An end before the start, or a window over 366 days, is 422; 366 days is fine.

    Covers: KAL-API-012
    """
    main_id, savings_id = await _accounts(session)
    pt_id = (await api_client.post(f"{BASE}/", json=_standing_order(main_id, savings_id))).json()[
        "id"
    ]
    url = f"{BASE}/{pt_id}/occurrences"
    backwards = await api_client.get(url, params={"start": "2026-03-01", "end": "2026-02-28"})
    too_long = await api_client.get(url, params={"start": "2026-01-01", "end": "2027-01-03"})
    longest = await api_client.get(url, params={"start": "2026-01-01", "end": "2027-01-02"})
    assert [backwards.status_code, too_long.status_code, longest.status_code] == [422, 422, 200]
    assert backwards.json()["error"]["code"] == "validation_error"
    assert len(longest.json()) == 12  # the 10th of each month in 2026


async def test_unknown_id_is_404(api_client: AsyncClient) -> None:
    """Every route on a plan that does not exist is 404.

    Covers: KAL-API-012
    """
    missing = f"{BASE}/999999"
    responses = [
        await api_client.get(missing),
        await api_client.put(missing, json={"amount": "1.00"}),
        await api_client.delete(missing),
        await api_client.post(f"{missing}/toggle-active"),
        await api_client.get(
            f"{missing}/occurrences", params={"start": "2026-01-01", "end": "2026-01-31"}
        ),
    ]
    assert [r.status_code for r in responses] == [404] * 5
    assert all(r.json()["error"]["code"] == "not_found" for r in responses)


def test_every_operation_has_a_summary() -> None:
    """The OpenAPI schema names every planned-transaction operation.

    Covers: KAL-API-012
    """
    app = FastAPI()
    app.include_router(create_api_router())
    paths = app.openapi()["paths"]
    ops = [
        op
        for path, item in paths.items()
        if path.startswith("/api/v1/planned-transactions")
        for op in item.values()
    ]
    assert len(ops) == 7
    assert all(op.get("summary") for op in ops)
