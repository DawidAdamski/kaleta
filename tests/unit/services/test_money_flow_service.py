# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for MoneyFlowService."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import TransactionCreate, TransactionSplitCreate
from kaleta.services import AccountService, CategoryService, TransactionService
from kaleta.services.money_flow_service import (
    DEFICIT_ID,
    OUT_OTHER_ID,
    POOL_ID,
    SURPLUS_ID,
    MoneyFlowService,
    month_bounds,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture
def svc(session: AsyncSession) -> MoneyFlowService:
    return MoneyFlowService(session)


async def _make_account(session: AsyncSession, name: str = "Checking") -> int:
    acc = await AccountService(session).create(
        AccountCreate(name=name, type=AccountType.CHECKING, balance=Decimal("0.00"))
    )
    return acc.id


async def _make_category(
    session: AsyncSession,
    name: str,
    cat_type: CategoryType = CategoryType.EXPENSE,
    parent_id: int | None = None,
) -> int:
    cat = await CategoryService(session).create(
        CategoryCreate(name=name, type=cat_type, parent_id=parent_id)
    )
    return cat.id


async def _make_tx(
    session: AsyncSession,
    *,
    account_id: int,
    category_id: int | None,
    amount: Decimal,
    tx_type: TransactionType,
    date: datetime.date,
    is_internal_transfer: bool = False,
) -> None:
    await TransactionService(session).create(
        TransactionCreate(
            account_id=account_id,
            category_id=category_id,
            amount=amount,
            type=tx_type,
            date=date,
            description="",
            is_internal_transfer=is_internal_transfer,
        )
    )


# ── Scenarios ─────────────────────────────────────────────────────────────────


class TestMoneyFlowBuild:
    async def test_income_to_budget_to_expenses(
        self, svc: MoneyFlowService, session: AsyncSession
    ) -> None:
        """Covers: KAL-FLW-001"""
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food", CategoryType.EXPENSE)
        rent = await _make_category(session, "Rent", CategoryType.EXPENSE)
        d = datetime.date(2025, 6, 15)
        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("5000"),
            tx_type=TransactionType.INCOME,
            date=d,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("400"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=rent,
            amount=Decimal("1500"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )

        start, end = month_bounds(2025, 6)
        flow = await svc.build(start, end)

        assert flow.total_in == Decimal("5000")
        assert flow.total_out == Decimal("1900")
        assert flow.net == Decimal("3100")
        node_ids = {n.id for n in flow.nodes}
        assert {f"in:{salary}", POOL_ID, f"out:{food}", f"out:{rent}", SURPLUS_ID} <= node_ids

        by_edge = {(lnk.source, lnk.target): lnk.amount for lnk in flow.links}
        assert by_edge[(f"in:{salary}", POOL_ID)] == Decimal("5000")
        assert by_edge[(POOL_ID, f"out:{food}")] == Decimal("400")
        assert by_edge[(POOL_ID, f"out:{rent}")] == Decimal("1500")
        assert by_edge[(POOL_ID, SURPLUS_ID)] == Decimal("3100")

    async def test_surplus_and_deficit_balancing(
        self, svc: MoneyFlowService, session: AsyncSession
    ) -> None:
        """Covers: KAL-FLW-002"""
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food", CategoryType.EXPENSE)

        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("1000"),
            tx_type=TransactionType.INCOME,
            date=datetime.date(2025, 3, 1),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("400"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2025, 3, 2),
        )
        surplus_flow = await svc.build(*month_bounds(2025, 3))
        assert surplus_flow.net == Decimal("600")
        assert any(n.id == SURPLUS_ID and n.kind == "surplus" for n in surplus_flow.nodes)
        assert not any(n.id == DEFICIT_ID for n in surplus_flow.nodes)

        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("2000"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2025, 4, 5),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("500"),
            tx_type=TransactionType.INCOME,
            date=datetime.date(2025, 4, 5),
        )
        deficit_flow = await svc.build(*month_bounds(2025, 4))
        assert deficit_flow.net == Decimal("-1500")
        assert any(n.id == DEFICIT_ID and n.kind == "deficit" for n in deficit_flow.nodes)
        assert not any(n.id == SURPLUS_ID for n in deficit_flow.nodes)
        by_edge = {(lnk.source, lnk.target): lnk.amount for lnk in deficit_flow.links}
        assert by_edge[(DEFICIT_ID, POOL_ID)] == Decimal("1500")

    async def test_split_lines_land_in_own_categories(
        self, svc: MoneyFlowService, session: AsyncSession
    ) -> None:
        """Covers: KAL-FLW-003"""
        acc = await _make_account(session)
        groceries = await _make_category(session, "Groceries")
        alcohol = await _make_category(session, "Alcohol")
        await TransactionService(session).create(
            TransactionCreate(
                account_id=acc,
                category_id=None,
                amount=Decimal("214.50"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2025, 6, 10),
                description="Biedronka",
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=groceries, amount=Decimal("180.00")),
                    TransactionSplitCreate(category_id=alcohol, amount=Decimal("34.50")),
                ],
            )
        )
        flow = await svc.build(*month_bounds(2025, 6))
        by_edge = {(lnk.source, lnk.target): lnk.amount for lnk in flow.links}
        assert by_edge[(POOL_ID, f"out:{groceries}")] == Decimal("180.00")
        assert by_edge[(POOL_ID, f"out:{alcohol}")] == Decimal("34.50")

    async def test_internal_transfers_appear_as_account_edges(
        self, svc: MoneyFlowService, session: AsyncSession
    ) -> None:
        """Covers: KAL-FLW-004"""
        from kaleta.schemas.transaction import TransactionCreate

        checking = await _make_account(session, "Checking MF")
        savings = await _make_account(session, "Savings MF")
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food", CategoryType.EXPENSE)
        d = datetime.date(2025, 6, 15)
        await _make_tx(
            session,
            account_id=checking,
            category_id=salary,
            amount=Decimal("3000"),
            tx_type=TransactionType.INCOME,
            date=d,
        )
        await _make_tx(
            session,
            account_id=checking,
            category_id=food,
            amount=Decimal("200"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )
        await TransactionService(session).create_transfer(
            TransactionCreate(
                account_id=checking,
                amount=Decimal("500"),
                type=TransactionType.TRANSFER,
                date=d,
                description="to savings",
                is_internal_transfer=True,
            ),
            TransactionCreate(
                account_id=savings,
                amount=Decimal("500"),
                type=TransactionType.TRANSFER,
                date=d,
                description="from checking",
                is_internal_transfer=True,
            ),
        )
        flow = await svc.build(*month_bounds(2025, 6), mode="accounts")
        assert flow.total_in == Decimal("3000")
        assert flow.total_out == Decimal("200")
        assert flow.total_transfers == Decimal("500")
        assert flow.mode == "accounts"
        assert any(n.id == f"acc:{checking}" and n.kind == "account" for n in flow.nodes)
        assert any(n.id == f"acc:{savings}" and n.kind == "account" for n in flow.nodes)
        by_edge = {(lnk.source, lnk.target): lnk.amount for lnk in flow.links}
        assert by_edge[(f"acc:{checking}", f"acc:{savings}")] == Decimal("500")
        # Income lands on the account, expenses leave it.
        assert by_edge[(f"in:{salary}", f"acc:{checking}")] == Decimal("3000")
        assert by_edge[(f"acc:{checking}", f"out:{food}")] == Decimal("200")

    async def test_budget_mode_hides_transfers(
        self, svc: MoneyFlowService, session: AsyncSession
    ) -> None:
        from kaleta.schemas.transaction import TransactionCreate

        checking = await _make_account(session, "Checking Bud")
        savings = await _make_account(session, "Savings Bud")
        salary = await _make_category(session, "Salary Bud", CategoryType.INCOME)
        d = datetime.date(2025, 7, 1)
        await _make_tx(
            session,
            account_id=checking,
            category_id=salary,
            amount=Decimal("1000"),
            tx_type=TransactionType.INCOME,
            date=d,
        )
        await TransactionService(session).create_transfer(
            TransactionCreate(
                account_id=checking,
                amount=Decimal("100"),
                type=TransactionType.TRANSFER,
                date=d,
                description="to savings",
                is_internal_transfer=True,
            ),
            TransactionCreate(
                account_id=savings,
                amount=Decimal("100"),
                type=TransactionType.TRANSFER,
                date=d,
                description="from checking",
                is_internal_transfer=True,
            ),
        )
        flow = await svc.build(*month_bounds(2025, 7), mode="budget")
        assert flow.mode == "budget"
        assert flow.total_transfers == Decimal("0")
        assert not any(n.kind == "account" for n in flow.nodes)
        assert any(n.id == POOL_ID for n in flow.nodes)

    async def test_top_n_folds_remainder(
        self, svc: MoneyFlowService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        d = datetime.date(2025, 6, 10)
        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("10000"),
            tx_type=TransactionType.INCOME,
            date=d,
        )
        for i in range(5):
            cat = await _make_category(session, f"Cat{i}")
            await _make_tx(
                session,
                account_id=acc,
                category_id=cat,
                amount=Decimal(str(100 * (5 - i))),
                tx_type=TransactionType.EXPENSE,
                date=d,
            )
        flow = await svc.build(*month_bounds(2025, 6), top_n=2)
        assert any(n.id == OUT_OTHER_ID for n in flow.nodes)
        by_edge = {(lnk.source, lnk.target): lnk.amount for lnk in flow.links}
        assert by_edge[(POOL_ID, OUT_OTHER_ID)] == Decimal("600")  # 300+200+100

    async def test_uncategorised_bucket(self, svc: MoneyFlowService, session: AsyncSession) -> None:
        from kaleta.models.transaction import Transaction

        acc = await _make_account(session)
        # Bypass schema — uncategorised expenses are legacy / import edge cases.
        session.add(
            Transaction(
                account_id=acc,
                category_id=None,
                amount=Decimal("50"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2025, 6, 1),
                description="legacy",
                is_internal_transfer=False,
                is_split=False,
            )
        )
        await session.commit()
        flow = await svc.build(*month_bounds(2025, 6))
        assert any(n.id == "out:uncategorised" for n in flow.nodes)

    async def test_empty_period(self, svc: MoneyFlowService) -> None:
        flow = await svc.build(*month_bounds(2020, 1))
        assert flow.nodes == []
        assert flow.links == []
        assert flow.total_in == Decimal("0")
        assert flow.period_label == "2020-01"

    async def test_name_collision_uses_namespaced_ids_and_unique_labels(
        self, svc: MoneyFlowService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        inc = await _make_category(session, "Other", CategoryType.INCOME)
        exp = await _make_category(session, "Other", CategoryType.EXPENSE)
        d = datetime.date(2025, 6, 1)
        await _make_tx(
            session,
            account_id=acc,
            category_id=inc,
            amount=Decimal("100"),
            tx_type=TransactionType.INCOME,
            date=d,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=exp,
            amount=Decimal("40"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )
        flow = await svc.build(*month_bounds(2025, 6))
        ids = {n.id for n in flow.nodes}
        assert f"in:{inc}" in ids
        assert f"out:{exp}" in ids
        labels = {n.id: n.label for n in flow.nodes}
        assert labels[f"in:{inc}"] != labels[f"out:{exp}"]
        assert "income" in labels[f"in:{inc}"]
        assert "expense" in labels[f"out:{exp}"]

    async def test_depth_two_expands_expense_children(
        self, svc: MoneyFlowService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food", CategoryType.EXPENSE)
        groceries = await _make_category(session, "Groceries", CategoryType.EXPENSE, parent_id=food)
        d = datetime.date(2025, 6, 1)
        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("1000"),
            tx_type=TransactionType.INCOME,
            date=d,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=groceries,
            amount=Decimal("200"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )
        flow = await svc.build(*month_bounds(2025, 6), depth=2)
        by_edge = {(lnk.source, lnk.target): lnk.amount for lnk in flow.links}
        assert by_edge[(POOL_ID, f"out:{food}")] == Decimal("200")
        assert by_edge[(f"out:{food}", f"out:{groceries}")] == Decimal("200")

    async def test_depth_one_rolls_children_into_parent(
        self, svc: MoneyFlowService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        food = await _make_category(session, "Food", CategoryType.EXPENSE)
        groceries = await _make_category(session, "Groceries", CategoryType.EXPENSE, parent_id=food)
        await _make_tx(
            session,
            account_id=acc,
            category_id=groceries,
            amount=Decimal("75"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2025, 6, 1),
        )
        flow = await svc.build(*month_bounds(2025, 6), depth=1)
        by_edge = {(lnk.source, lnk.target): lnk.amount for lnk in flow.links}
        assert by_edge[(POOL_ID, f"out:{food}")] == Decimal("75")
        assert f"out:{groceries}" not in {n.id for n in flow.nodes}
