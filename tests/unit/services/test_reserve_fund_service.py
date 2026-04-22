"""Unit tests for ReserveFundService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.reserve_fund import ReserveFundBackingMode, ReserveFundKind
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.reserve_fund import ReserveFundCreate, ReserveFundUpdate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, ReserveFundService, TransactionService


async def _make_account(session: AsyncSession, balance: Decimal) -> int:
    a = await AccountService(session).create(
        AccountCreate(name="Savings", type=AccountType.SAVINGS, balance=balance)
    )
    return a.id


async def _make_fund(
    session: AsyncSession,
    *,
    kind: ReserveFundKind = ReserveFundKind.EMERGENCY,
    target: Decimal = Decimal("10000"),
    account_id: int | None = None,
    multiplier: int | None = 3,
):
    svc = ReserveFundService(session)
    return await svc.create(
        ReserveFundCreate(
            name="Test fund",
            kind=kind,
            target_amount=target,
            backing_mode=ReserveFundBackingMode.ACCOUNT,
            backing_account_id=account_id,
            emergency_multiplier=multiplier if kind == ReserveFundKind.EMERGENCY else None,
        )
    )


# ── Validation ────────────────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_account_mode_requires_account_id(self):
        with pytest.raises(ValueError, match="backing_account_id is required"):
            ReserveFundCreate(
                name="X",
                kind=ReserveFundKind.VACATION,
                target_amount=Decimal("100"),
                backing_mode=ReserveFundBackingMode.ACCOUNT,
            )

    def test_account_mode_rejects_category_id(self):
        with pytest.raises(ValueError, match="backing_category_id must be null"):
            ReserveFundCreate(
                name="X",
                kind=ReserveFundKind.VACATION,
                target_amount=Decimal("100"),
                backing_mode=ReserveFundBackingMode.ACCOUNT,
                backing_account_id=1,
                backing_category_id=2,
            )

    def test_envelope_mode_requires_category_id(self):
        with pytest.raises(ValueError, match="backing_category_id is required"):
            ReserveFundCreate(
                name="X",
                kind=ReserveFundKind.VACATION,
                target_amount=Decimal("100"),
                backing_mode=ReserveFundBackingMode.ENVELOPE,
            )


# ── CRUD ──────────────────────────────────────────────────────────────────────


class TestCrud:
    async def test_create_persists_fund(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        fund = await _make_fund(session, account_id=acc)
        assert fund.id is not None
        assert fund.kind == ReserveFundKind.EMERGENCY
        assert fund.target_amount == Decimal("10000")
        assert fund.emergency_multiplier == 3

    async def test_list_returns_all(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        await _make_fund(session, account_id=acc, kind=ReserveFundKind.EMERGENCY)
        await _make_fund(
            session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None
        )
        funds = await ReserveFundService(session).list()
        assert len(funds) == 2

    async def test_update_mutates_target(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        fund = await _make_fund(session, account_id=acc)
        svc = ReserveFundService(session)
        updated = await svc.update(fund.id, ReserveFundUpdate(target_amount=Decimal("99999")))
        assert updated is not None
        assert updated.target_amount == Decimal("99999")

    async def test_update_missing_returns_none(self, session: AsyncSession):
        svc = ReserveFundService(session)
        assert await svc.update(999, ReserveFundUpdate(name="X")) is None

    async def test_delete_removes(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        fund = await _make_fund(session, account_id=acc)
        svc = ReserveFundService(session)
        assert await svc.delete(fund.id) is True
        assert await svc.get(fund.id) is None

    async def test_delete_missing_returns_false(self, session: AsyncSession):
        assert await ReserveFundService(session).delete(999) is False


# ── Progress ──────────────────────────────────────────────────────────────────


class TestProgress:
    async def test_zero_target_yields_zero_pct(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("500"))
        fund = await _make_fund(
            session, account_id=acc, target=Decimal("0"), kind=ReserveFundKind.VACATION,
            multiplier=None,
        )
        svc = ReserveFundService(session)
        p = await svc.with_progress(fund)
        assert p.progress_pct == Decimal("0.00")
        assert p.current_balance == Decimal("500.00")

    async def test_progress_pct_tracks_balance(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("2500"))
        fund = await _make_fund(
            session, account_id=acc, target=Decimal("10000"),
            kind=ReserveFundKind.VACATION, multiplier=None,
        )
        svc = ReserveFundService(session)
        p = await svc.with_progress(fund)
        assert p.progress_pct == Decimal("0.25")
        assert p.current_balance == Decimal("2500.00")

    async def test_balance_can_exceed_target(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("15000"))
        fund = await _make_fund(
            session, account_id=acc, target=Decimal("10000"),
            kind=ReserveFundKind.VACATION, multiplier=None,
        )
        p = await ReserveFundService(session).with_progress(fund)
        assert p.progress_pct == Decimal("1.50")

    async def test_months_of_coverage_none_without_expenses(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("3000"))
        fund = await _make_fund(session, account_id=acc, multiplier=3)
        p = await ReserveFundService(session).with_progress(fund)
        assert p.months_of_coverage is None

    async def test_months_of_coverage_uses_trailing_90_days(
        self, session: AsyncSession
    ):
        # Savings: 9,000 PLN. Expenses over last 90d: 9,000 → monthly avg = 3,000 → 3 months.
        acc = await _make_account(session, Decimal("9000"))
        # Seed an expense category + transactions
        from kaleta.models.category import CategoryType
        from kaleta.schemas.category import CategoryCreate
        from kaleta.services import CategoryService
        cat = await CategoryService(session).create(
            CategoryCreate(name="Food", type=CategoryType.EXPENSE)
        )
        today = datetime.date(2026, 4, 22)
        tx_svc = TransactionService(session)
        for i in range(3):
            tx_date = today - datetime.timedelta(days=i * 30)
            await tx_svc.create(
                TransactionCreate(
                    amount=Decimal("3000"),
                    type=TransactionType.EXPENSE,
                    account_id=acc,
                    category_id=cat.id,
                    date=tx_date,
                    description=f"expense-{i}",
                )
            )

        fund = await _make_fund(session, account_id=acc, multiplier=3)
        p = await ReserveFundService(session).with_progress(fund, today=today)
        # 9000 (3 × 3000) / 90 days × 30 days = 3000/month. 9000 / 3000 = 3 months.
        assert p.months_of_coverage == Decimal("3.0")

    async def test_months_of_coverage_only_for_emergency(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("1000"))
        fund = await _make_fund(
            session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None
        )
        p = await ReserveFundService(session).with_progress(fund)
        assert p.months_of_coverage is None

    async def test_list_with_progress_iterates_all(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("100"))
        await _make_fund(session, account_id=acc, kind=ReserveFundKind.EMERGENCY)
        await _make_fund(
            session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None
        )
        items = await ReserveFundService(session).list_with_progress()
        assert len(items) == 2
        assert {i.kind for i in items} == {
            ReserveFundKind.EMERGENCY,
            ReserveFundKind.VACATION,
        }
