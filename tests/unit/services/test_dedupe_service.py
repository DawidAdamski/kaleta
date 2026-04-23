"""Unit tests for DedupeService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import Category, CategoryType
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.services import (
    AccountService,
    BudgetService,
    CategoryService,
    DedupeService,
)
from kaleta.services.dedupe_service import (
    _descriptions_look_alike,
    _levenshtein,
    _levenshtein_close,
    _normalise_name,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


async def _make_account(session: AsyncSession) -> int:
    a = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING, balance=Decimal("0"))
    )
    return a.id


async def _make_category(
    session: AsyncSession, name: str, *, type: CategoryType = CategoryType.EXPENSE
) -> int:
    c = await CategoryService(session).create(CategoryCreate(name=name, type=type))
    return c.id


async def _make_payee(session: AsyncSession, name: str) -> Payee:
    payee = Payee(name=name)
    session.add(payee)
    await session.commit()
    await session.refresh(payee)
    return payee


async def _make_tx(
    session: AsyncSession,
    *,
    account_id: int,
    amount: Decimal,
    date: datetime.date,
    description: str,
    payee_id: int | None = None,
    category_id: int | None = None,
    is_internal: bool = False,
) -> Transaction:
    tx = Transaction(
        account_id=account_id,
        category_id=category_id,
        payee_id=payee_id,
        type=(TransactionType.EXPENSE if amount < 0 else TransactionType.INCOME),
        amount=amount,
        date=date,
        description=description,
        is_internal_transfer=is_internal,
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx


# ── Normaliser + Levenshtein ─────────────────────────────────────────────────


class TestHelpers:
    def test_normalise_strips_case_diacritics_punct(self):
        assert _normalise_name("Żabka Sp. z o.o.") == "zabka sp z o o"
        assert _normalise_name("  Netflix  ") == "netflix"
        assert _normalise_name("") == ""

    def test_levenshtein_basic(self):
        assert _levenshtein("netflix", "netflix") == 0
        assert _levenshtein("netflix", "netflxx") == 1
        assert _levenshtein("kitten", "sitting") == 3

    def test_levenshtein_close_respects_short_threshold(self):
        assert _levenshtein_close("Netflix", "Netflxx") is True
        assert _levenshtein_close("Apple", "Amazon") is False

    def test_descriptions_look_alike_on_shared_token(self):
        assert _descriptions_look_alike("NETFLIX /LONDON", "NETFLIX.COM") is True
        assert _descriptions_look_alike("Biedronka", "Lidl") is False
        # Empty descriptions treated as unknown → match allowed.
        assert _descriptions_look_alike("", "anything") is True


# ── Duplicate transactions ───────────────────────────────────────────────────


class TestDuplicateTransactions:
    async def test_finds_exact_duplicates(self, session: AsyncSession):
        acc = await _make_account(session)
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-50.00"),
            date=datetime.date(2026, 4, 10),
            description="NETFLIX.COM",
        )
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-50.00"),
            date=datetime.date(2026, 4, 10),
            description="NETFLIX.COM",
        )
        groups = await DedupeService(session).duplicate_transactions()
        assert len(groups) == 1
        assert len(groups[0].items) == 2

    async def test_clusters_within_one_day(self, session: AsyncSession):
        acc = await _make_account(session)
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-25.00"),
            date=datetime.date(2026, 4, 10),
            description="NETFLIX",
        )
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-25.00"),
            date=datetime.date(2026, 4, 11),
            description="NETFLIX.COM",
        )
        groups = await DedupeService(session).duplicate_transactions()
        assert len(groups) == 1

    async def test_ignores_different_amounts(self, session: AsyncSession):
        acc = await _make_account(session)
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-50.00"),
            date=datetime.date(2026, 4, 10),
            description="NETFLIX",
        )
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-49.99"),
            date=datetime.date(2026, 4, 10),
            description="NETFLIX",
        )
        groups = await DedupeService(session).duplicate_transactions()
        assert groups == []

    async def test_ignores_internal_transfers(self, session: AsyncSession):
        acc = await _make_account(session)
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-100.00"),
            date=datetime.date(2026, 4, 10),
            description="X",
            is_internal=True,
        )
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-100.00"),
            date=datetime.date(2026, 4, 10),
            description="X",
            is_internal=True,
        )
        assert await DedupeService(session).duplicate_transactions() == []

    async def test_merge_transactions_deletes_others(self, session: AsyncSession):
        acc = await _make_account(session)
        tx1 = await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-50.00"),
            date=datetime.date(2026, 4, 10),
            description="NETFLIX",
        )
        tx2 = await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-50.00"),
            date=datetime.date(2026, 4, 10),
            description="NETFLIX",
        )
        svc = DedupeService(session)
        deleted = await svc.merge_transactions(keeper_id=tx1.id, other_ids=[tx2.id])
        assert deleted == 1
        remaining = (await session.execute(select(Transaction.id))).scalars().all()
        assert tx1.id in remaining
        assert tx2.id not in remaining


# ── Similar payees ───────────────────────────────────────────────────────────


class TestSimilarPayees:
    async def test_normalised_collision(self, session: AsyncSession):
        await _make_payee(session, "Netflix")
        await _make_payee(session, "NETFLIX.")
        await _make_payee(session, "Orange")
        groups = await DedupeService(session).similar_payees()
        assert len(groups) == 1
        names = {i.name for i in groups[0].items}
        assert names == {"Netflix", "NETFLIX."}

    async def test_levenshtein_close_catches_typo(self, session: AsyncSession):
        await _make_payee(session, "Netflix")
        await _make_payee(session, "Netflixx")  # one char off
        groups = await DedupeService(session).similar_payees()
        assert len(groups) == 1

    async def test_merge_payees_reassigns_transactions(self, session: AsyncSession):
        acc = await _make_account(session)
        keeper = await _make_payee(session, "Netflix")
        dupe = await _make_payee(session, "NETFLIX")
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-50.00"),
            date=datetime.date(2026, 4, 10),
            description="X",
            payee_id=dupe.id,
        )
        svc = DedupeService(session)
        merged = await svc.merge_payees(keeper_id=keeper.id, other_ids=[dupe.id])
        assert merged == 1
        remaining = (
            await session.execute(select(Payee.id))
        ).scalars().all()
        assert dupe.id not in remaining
        # Transaction was reassigned.
        reassigned = (
            await session.execute(
                select(Transaction.payee_id).where(Transaction.payee_id == keeper.id)
            )
        ).scalars().all()
        assert reassigned == [keeper.id]


# ── Redundant categories ─────────────────────────────────────────────────────


class TestRedundantCategories:
    async def test_normalised_collision_same_type(self, session: AsyncSession):
        await _make_category(session, "Food")
        await _make_category(session, "food")
        await _make_category(session, "Transport")
        groups = await DedupeService(session).redundant_categories()
        assert len(groups) == 1
        names = {i.name for i in groups[0].items}
        assert names == {"Food", "food"}

    async def test_income_expense_not_merged(self, session: AsyncSession):
        await _make_category(session, "Bonus", type=CategoryType.EXPENSE)
        await _make_category(session, "bonus", type=CategoryType.INCOME)
        assert await DedupeService(session).redundant_categories() == []

    async def test_merge_categories_reassigns_and_drops_conflicting_budgets(
        self, session: AsyncSession
    ):
        acc = await _make_account(session)
        keeper_id = await _make_category(session, "Food")
        victim_id = await _make_category(session, "FOOD")
        # Keeper has a budget for April 2026.
        await BudgetService(session).upsert(
            BudgetCreate(
                category_id=keeper_id, month=4, year=2026, amount=Decimal("500")
            )
        )
        # Victim has budgets for April (conflict, must be dropped) + May (move).
        await BudgetService(session).upsert(
            BudgetCreate(
                category_id=victim_id, month=4, year=2026, amount=Decimal("300")
            )
        )
        await BudgetService(session).upsert(
            BudgetCreate(
                category_id=victim_id, month=5, year=2026, amount=Decimal("400")
            )
        )
        # A transaction pointed at the victim.
        await _make_tx(
            session,
            account_id=acc,
            amount=Decimal("-20.00"),
            date=datetime.date(2026, 4, 3),
            description="X",
            category_id=victim_id,
        )
        merged = await DedupeService(session).merge_categories(
            keeper_id=keeper_id, other_ids=[victim_id]
        )
        assert merged == 1
        # Victim gone.
        cat_ids = (
            (await session.execute(select(Category.id))).scalars().all()
        )
        assert victim_id not in cat_ids
        # Keeper's April budget is still 500 (victim's 300 was dropped).
        budgets = await BudgetService(session).list()
        april = [b for b in budgets if b.month == 4 and b.category_id == keeper_id]
        may = [b for b in budgets if b.month == 5 and b.category_id == keeper_id]
        assert len(april) == 1 and april[0].amount == Decimal("500")
        assert len(may) == 1 and may[0].amount == Decimal("400")
        # Transaction was reassigned.
        tx_cats = (
            await session.execute(select(Transaction.category_id))
        ).scalars().all()
        assert all(c == keeper_id for c in tx_cats if c is not None)
