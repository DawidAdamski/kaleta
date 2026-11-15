# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/reserve-funds/{fund_id}/items`` and ``/plan`` — the irregular fund's items.

Covers: KAL-API-011

Names and amounts are the literals of KAL-API-011.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.gift import GiftCellSet, GiftName
from kaleta.schemas.reserve_fund import ReserveFundCreate, ReserveFundKind
from kaleta.services import AccountService, GiftService, ReserveFundService

BASE = "/api/v1/reserve-funds"


async def _fund(
    session: AsyncSession,
    *,
    name: str = "Wydatki nieregularne",
    kind: ReserveFundKind = ReserveFundKind.IRREGULAR,
) -> int:
    account = await AccountService(session).create(
        AccountCreate(name=f"Konto {name}", type=AccountType.SAVINGS, balance=Decimal("0.00"))
    )
    fund = await ReserveFundService(session).create(
        ReserveFundCreate(
            name=name,
            kind=kind,
            target_amount=Decimal("3000.00"),
            backing_account_id=account.id,
        )
    )
    await session.commit()
    return fund.id


async def _gift(session: AsyncSession, amount: str) -> None:
    gifts = GiftService(session)
    person = await gifts.add_person(GiftName(name="Mama"))
    occasion = await gifts.add_occasion(GiftName(name="Urodziny"))
    await gifts.set_cell(
        datetime.date.today().year, person.id, occasion.id, GiftCellSet(amount=Decimal(amount))
    )
    await session.commit()


async def test_irregular_items_round_trip(api_client: AsyncClient, session: AsyncSession) -> None:
    """Create → list → plan (with the gifts line) → update → delete.

    Covers: KAL-API-011
    """
    fund_id = await _fund(session)
    items = f"{BASE}/{fund_id}/items"

    car = await api_client.post(
        items, json={"name": "Ubezpieczenie auta", "yearly_amount": "1200.00", "due_month": 3}
    )
    assert car.status_code == 201, car.text
    assert car.json()["monthly_contribution"] == "120.00"
    assert car.json()["fund_id"] == fund_id
    car_id = car.json()["id"]

    tax = await api_client.post(
        items, json={"name": "Podatek od nieruchomości", "yearly_amount": "600.00"}
    )
    assert tax.status_code == 201
    tax_id = tax.json()["id"]

    listed = await api_client.get(items)
    assert listed.status_code == 200
    assert [i["name"] for i in listed.json()] == ["Ubezpieczenie auta", "Podatek od nieruchomości"]

    await _gift(session, "300.00")
    plan = await api_client.get(f"{BASE}/{fund_id}/plan")
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert [d["source"] for d in body["derived_items"]] == ["gifts"]
    assert body["monthly_total"] == "210.00"
    assert body["fund_name"] == "Wydatki nieregularne"

    updated = await api_client.put(f"{items}/{car_id}", json={"yearly_amount": "1500.00"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["monthly_contribution"] == "150.00"
    assert updated.json()["name"] == "Ubezpieczenie auta"

    deleted = await api_client.delete(f"{items}/{tax_id}")
    assert deleted.status_code == 204
    assert [i["id"] for i in (await api_client.get(items)).json()] == [car_id]


async def test_item_through_another_fund_is_404(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """An item addressed through a fund it does not belong to is not found, and unchanged.

    Covers: KAL-API-011
    """
    fund_id = await _fund(session)
    other_id = await _fund(session, name="Drugi fundusz")
    car = await api_client.post(
        f"{BASE}/{fund_id}/items", json={"name": "Ubezpieczenie auta", "yearly_amount": "1200.00"}
    )
    car_id = car.json()["id"]

    wrong = f"{BASE}/{other_id}/items/{car_id}"
    put = await api_client.put(wrong, json={"yearly_amount": "1.00"})
    delete = await api_client.delete(wrong)
    assert [put.status_code, delete.status_code] == [404, 404]
    assert put.json()["error"]["code"] == "not_found"

    still = (await api_client.get(f"{BASE}/{fund_id}/items")).json()
    assert [(i["id"], i["yearly_amount"]) for i in still] == [(car_id, "1200.00")]


async def test_unknown_fund_is_404(api_client: AsyncClient) -> None:
    """Every items route on a fund that does not exist is 404.

    Covers: KAL-API-011
    """
    missing = f"{BASE}/999999"
    responses = [
        await api_client.get(f"{missing}/items"),
        await api_client.get(f"{missing}/plan"),
        await api_client.post(f"{missing}/items", json={"name": "x", "yearly_amount": "1.00"}),
        await api_client.put(f"{missing}/items/1", json={"name": "y"}),
        await api_client.delete(f"{missing}/items/1"),
    ]
    assert [r.status_code for r in responses] == [404] * 5


async def test_emergency_fund_items_are_422(api_client: AsyncClient, session: AsyncSession) -> None:
    """Only an irregular-expenses fund has items.

    Covers: KAL-API-011
    """
    fund_id = await _fund(session, name="Poduszka", kind=ReserveFundKind.EMERGENCY)
    responses = [
        await api_client.get(f"{BASE}/{fund_id}/items"),
        await api_client.get(f"{BASE}/{fund_id}/plan"),
        await api_client.post(
            f"{BASE}/{fund_id}/items", json={"name": "x", "yearly_amount": "1.00"}
        ),
    ]
    assert [r.status_code for r in responses] == [422] * 3
    assert all(r.json()["error"]["code"] == "validation_error" for r in responses)
