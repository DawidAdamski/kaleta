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


@pytest.mark.asyncio
async def test_reports_money_flow(api_client) -> None:
    today = date.today()
    start = today.replace(day=1)
    end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)

    cat = await api_client.post(
        "/api/v1/categories/",
        json={"name": "Salary MF", "type": "income"},
    )
    assert cat.status_code == 201
    salary_id = cat.json()["id"]

    acc = await api_client.post(
        "/api/v1/accounts/",
        json={"name": "MF Checking", "type": "checking", "balance": "0.00", "currency": "PLN"},
    )
    assert acc.status_code == 201
    acc_id = acc.json()["id"]

    tx = await api_client.post(
        "/api/v1/transactions/",
        json={
            "account_id": acc_id,
            "category_id": salary_id,
            "amount": "2500.00",
            "type": "income",
            "date": today.isoformat(),
            "description": "pay",
        },
    )
    assert tx.status_code == 201

    resp = await api_client.get(
        "/api/v1/reports/money-flow",
        params={"start": start.isoformat(), "end": end.isoformat(), "top_n": 12, "depth": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["total_in"]) == Decimal("2500.00")
    assert body["period_label"]
    assert any(n["id"] == "pool" for n in body["nodes"])
    assert any(n["kind"] == "surplus" for n in body["nodes"])


@pytest.mark.asyncio
async def test_reports_money_flow_rejects_inverted_range(api_client) -> None:
    resp = await api_client.get(
        "/api/v1/reports/money-flow",
        params={"start": "2025-06-30", "end": "2025-06-01"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reports_money_flow_split_lines(api_client) -> None:
    """Covers: KAL-FLW-003"""
    today = date.today()
    start = today.replace(day=1)
    end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)

    groceries = await api_client.post(
        "/api/v1/categories/", json={"name": "MF Groceries", "type": "expense"}
    )
    alcohol = await api_client.post(
        "/api/v1/categories/", json={"name": "MF Alcohol", "type": "expense"}
    )
    assert groceries.status_code == 201
    assert alcohol.status_code == 201
    groceries_id = groceries.json()["id"]
    alcohol_id = alcohol.json()["id"]

    acc = await api_client.post(
        "/api/v1/accounts/",
        json={"name": "MF Split Acc", "type": "checking", "balance": "0.00", "currency": "PLN"},
    )
    assert acc.status_code == 201
    acc_id = acc.json()["id"]

    tx = await api_client.post(
        "/api/v1/transactions/",
        json={
            "account_id": acc_id,
            "amount": "214.50",
            "type": "expense",
            "date": today.isoformat(),
            "description": "Lidl",
            "is_split": True,
            "splits": [
                {"category_id": groceries_id, "amount": "180.00"},
                {"category_id": alcohol_id, "amount": "34.50"},
            ],
        },
    )
    assert tx.status_code == 201

    resp = await api_client.get(
        "/api/v1/reports/money-flow",
        params={"start": start.isoformat(), "end": end.isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    by_edge = {(lnk["source"], lnk["target"]): Decimal(lnk["amount"]) for lnk in body["links"]}
    assert by_edge[("pool", f"out:{groceries_id}")] == Decimal("180.00")
    assert by_edge[("pool", f"out:{alcohol_id}")] == Decimal("34.50")


@pytest.mark.asyncio
async def test_reports_money_flow_shows_internal_transfers(api_client, db_engine) -> None:
    """Covers: KAL-FLW-004"""
    from kaleta.models.account import AccountType
    from kaleta.models.category import CategoryType
    from kaleta.models.transaction import TransactionType, TransferDirection
    from kaleta.schemas.account import AccountCreate
    from kaleta.schemas.category import CategoryCreate
    from kaleta.schemas.transaction import TransactionCreate
    from kaleta.services import AccountService, CategoryService, TransactionService
    from tests.conftest import make_session_factory

    today = date.today()
    start = today.replace(day=1)
    end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)

    factory = make_session_factory(db_engine)
    async with factory() as session:
        checking = await AccountService(session).create(
            AccountCreate(name="MF Src Acc", type=AccountType.CHECKING, balance=Decimal("0"))
        )
        savings = await AccountService(session).create(
            AccountCreate(name="MF Dst Acc", type=AccountType.SAVINGS, balance=Decimal("0"))
        )
        salary = await CategoryService(session).create(
            CategoryCreate(name="MF Xfer Salary", type=CategoryType.INCOME)
        )
        food = await CategoryService(session).create(
            CategoryCreate(name="MF Xfer Food", type=CategoryType.EXPENSE)
        )
        await TransactionService(session).create(
            TransactionCreate(
                account_id=checking.id,
                category_id=salary.id,
                amount=Decimal("1000.00"),
                type=TransactionType.INCOME,
                date=today,
                description="pay",
            )
        )
        await TransactionService(session).create(
            TransactionCreate(
                account_id=checking.id,
                category_id=food.id,
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                date=today,
                description="food",
            )
        )
        await TransactionService(session).create_transfer(
            TransactionCreate(
                account_id=checking.id,
                amount=Decimal("250.00"),
                type=TransactionType.TRANSFER,
                transfer_direction=TransferDirection.OUT,
                date=today,
                description="to savings",
                is_internal_transfer=True,
            ),
            TransactionCreate(
                account_id=savings.id,
                amount=Decimal("250.00"),
                type=TransactionType.TRANSFER,
                transfer_direction=TransferDirection.IN,
                date=today,
                description="from checking",
                is_internal_transfer=True,
            ),
        )
        checking_id, savings_id = checking.id, savings.id

    resp = await api_client.get(
        "/api/v1/reports/money-flow",
        params={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "mode": "accounts",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "accounts"
    assert Decimal(body["total_in"]) == Decimal("1000.00")
    assert Decimal(body["total_out"]) == Decimal("100.00")
    assert Decimal(body["total_transfers"]) == Decimal("250.00")
    node_ids = {n["id"] for n in body["nodes"]}
    assert f"acc:{checking_id}" in node_ids
    assert f"acc:{savings_id}" in node_ids
    by_edge = {(lnk["source"], lnk["target"]): Decimal(lnk["amount"]) for lnk in body["links"]}
    assert by_edge[(f"acc:{checking_id}", f"acc:{savings_id}")] == Decimal("250.00")


@pytest.mark.asyncio
async def test_reports_money_flow_transfer_ribbon_follows_stored_direction(
    api_client, db_engine
) -> None:
    """Covers: KAL-FLW-005

    A transfer pair formed after the fact (``pair_as_transfer`` / import
    "accept") can have the *incoming* leg with the lower id. The ribbon must
    follow the stored ``transfer_direction`` (OUT = source), not id order,
    which would draw it backwards.
    """
    from kaleta.models.account import AccountType
    from kaleta.models.category import CategoryType
    from kaleta.models.transaction import TransactionType
    from kaleta.schemas.account import AccountCreate
    from kaleta.schemas.category import CategoryCreate
    from kaleta.schemas.transaction import TransactionCreate
    from kaleta.services import AccountService, CategoryService, TransactionService
    from tests.conftest import make_session_factory

    today = date.today()
    start = today.replace(day=1)
    end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)

    factory = make_session_factory(db_engine)
    async with factory() as session:
        source = await AccountService(session).create(
            AccountCreate(name="MF Pair Source", type=AccountType.CHECKING, balance=Decimal("0"))
        )
        destination = await AccountService(session).create(
            AccountCreate(
                name="MF Pair Destination", type=AccountType.SAVINGS, balance=Decimal("0")
            )
        )
        in_cat = await CategoryService(session).create(
            CategoryCreate(name="MF Pair In", type=CategoryType.INCOME)
        )
        out_cat = await CategoryService(session).create(
            CategoryCreate(name="MF Pair Out", type=CategoryType.EXPENSE)
        )
        tx_svc = TransactionService(session)
        # The ARRIVING row is recorded first → it gets the LOWER id. Old
        # id-order inference would pick it as the source and draw the ribbon
        # backwards.
        arriving = await tx_svc.create(
            TransactionCreate(
                account_id=destination.id,
                category_id=in_cat.id,
                amount=Decimal("300.00"),
                type=TransactionType.INCOME,
                date=today,
                description="arrived from source",
            )
        )
        leaving = await tx_svc.create(
            TransactionCreate(
                account_id=source.id,
                category_id=out_cat.id,
                amount=Decimal("300.00"),
                type=TransactionType.EXPENSE,
                date=today,
                description="left to destination",
            )
        )
        assert arriving.id < leaving.id
        # expense_id is the leg the money left (OUT), income_id where it arrived (IN).
        await tx_svc.pair_as_transfer(expense_id=leaving.id, income_id=arriving.id)
        source_id, destination_id = source.id, destination.id

    resp = await api_client.get(
        "/api/v1/reports/money-flow",
        params={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "mode": "accounts",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["total_transfers"]) == Decimal("300.00")
    by_edge = {(lnk["source"], lnk["target"]): Decimal(lnk["amount"]) for lnk in body["links"]}
    # Money leaves the source and arrives on the destination — not backwards.
    assert by_edge[(f"acc:{source_id}", f"acc:{destination_id}")] == Decimal("300.00")
    assert (f"acc:{destination_id}", f"acc:{source_id}") not in by_edge
