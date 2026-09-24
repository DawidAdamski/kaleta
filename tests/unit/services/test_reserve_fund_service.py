# SPDX-License-Identifier: AGPL-3.0-or-later
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
from kaleta.schemas.reserve_fund import (
    ReserveFundCreate,
    ReserveFundUpdate,
    ReserveFundWithProgress,
)
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
        await _make_fund(session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None)
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
            session,
            account_id=acc,
            target=Decimal("0"),
            kind=ReserveFundKind.VACATION,
            multiplier=None,
        )
        svc = ReserveFundService(session)
        p = await svc.with_progress(fund)
        assert p.progress_pct == Decimal("0.00")
        assert p.current_balance == Decimal("500.00")

    async def test_progress_pct_tracks_balance(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("2500"))
        fund = await _make_fund(
            session,
            account_id=acc,
            target=Decimal("10000"),
            kind=ReserveFundKind.VACATION,
            multiplier=None,
        )
        svc = ReserveFundService(session)
        p = await svc.with_progress(fund)
        assert p.progress_pct == Decimal("0.25")
        assert p.current_balance == Decimal("2500.00")

    async def test_balance_can_exceed_target(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("15000"))
        fund = await _make_fund(
            session,
            account_id=acc,
            target=Decimal("10000"),
            kind=ReserveFundKind.VACATION,
            multiplier=None,
        )
        p = await ReserveFundService(session).with_progress(fund)
        assert p.progress_pct == Decimal("1.50")

    async def test_months_of_coverage_none_without_expenses(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("3000"))
        fund = await _make_fund(session, account_id=acc, multiplier=3)
        p = await ReserveFundService(session).with_progress(fund)
        assert p.months_of_coverage is None

    async def test_months_of_coverage_uses_trailing_90_days(self, session: AsyncSession):
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
        await _make_fund(session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None)
        items = await ReserveFundService(session).list_with_progress()
        assert len(items) == 2
        assert {i.kind for i in items} == {
            ReserveFundKind.EMERGENCY,
            ReserveFundKind.VACATION,
        }


# ── Spending-derived target ───────────────────────────────────────────────────


async def _seed_expenses(
    session: AsyncSession, account_id: int, amounts_by_days_ago: list[tuple[int, Decimal]], today
) -> None:
    from kaleta.models.category import CategoryType
    from kaleta.schemas.category import CategoryCreate
    from kaleta.services import CategoryService

    cat = await CategoryService(session).create(
        CategoryCreate(name="Living", type=CategoryType.EXPENSE)
    )
    tx_svc = TransactionService(session)
    for days_ago, amount in amounts_by_days_ago:
        await tx_svc.create(
            TransactionCreate(
                amount=amount,
                type=TransactionType.EXPENSE,
                account_id=account_id,
                category_id=cat.id,
                date=today - datetime.timedelta(days=days_ago),
                description=f"expense-{days_ago}",
            )
        )


class TestDerivedTarget:
    TODAY = datetime.date(2026, 9, 25)

    async def _security_fund(self, session: AsyncSession, balance: Decimal):
        acc = await _make_account(session, balance)
        # 12 monthly expenses of 5200.00 inside the last 12 months, plus one
        # older expense that must fall outside the window.
        await _seed_expenses(
            session,
            acc,
            [(5 + i * 30, Decimal("5200.00")) for i in range(12)] + [(400, Decimal("99999.00"))],
            self.TODAY,
        )
        fund = await ReserveFundService(session).create(
            ReserveFundCreate(
                name="Security fund",
                kind=ReserveFundKind.EMERGENCY,
                target_amount=Decimal("0"),
                backing_account_id=acc,
                emergency_multiplier=3,
                target_from_spending=True,
            )
        )
        return fund

    async def test_target_derives_from_12_month_spending(self, session: AsyncSession):
        """Covers: KAL-FND-002

        Average monthly expenses over the last 12 months are 5200.00 and
        "Security fund" is a 3-month reserve: the Reserves panel shows a
        15600.00 target.
        """
        fund = await self._security_fund(session, Decimal("0"))
        svc = ReserveFundService(session)

        assert await svc.derived_target(fund, today=self.TODAY) == Decimal("15600.00")
        [shown] = await svc.list_with_progress(today=self.TODAY)
        assert shown.name == "Security fund"
        assert shown.target_from_spending is True
        assert shown.target_amount == Decimal("15600.00")

    async def test_progress_and_coverage_use_their_own_windows(self, session: AsyncSession):
        # Balance 7800.00 against the derived 15600.00 → 50%. Coverage keeps
        # the 90-day window: 3 × 5200.00 fall in it → 5200.00/month → 1.5.
        fund = await self._security_fund(session, Decimal("7800.00"))
        p = await ReserveFundService(session).with_progress(fund, today=self.TODAY)
        assert p.progress_pct == Decimal("0.50")
        assert p.months_of_coverage == Decimal("1.5")

    async def test_manual_target_is_untouched_without_the_flag(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        await _seed_expenses(session, acc, [(10, Decimal("5200.00"))], self.TODAY)
        fund = await _make_fund(session, account_id=acc, target=Decimal("3000.00"))
        p = await ReserveFundService(session).with_progress(fund, today=self.TODAY)
        assert p.target_from_spending is False
        assert p.target_amount == Decimal("3000.00")

    async def test_derived_target_is_none_without_multiplier(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        fund = await _make_fund(
            session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None
        )
        assert await ReserveFundService(session).derived_target(fund) is None

    async def test_save_snapshots_the_derived_target(self, session: AsyncSession):
        # The stored column holds the derived figure as of the save, for
        # readers that take target_amount as-is (wizard projection, REST).
        acc = await _make_account(session, Decimal("0"))
        await _seed_expenses(session, acc, [(0, Decimal("1200.00"))], datetime.date.today())
        fund = await _make_fund(session, account_id=acc, target=Decimal("3000.00"))
        svc = ReserveFundService(session)
        updated = await svc.update(fund.id, ReserveFundUpdate(target_from_spending=True))
        assert updated is not None
        assert updated.target_amount == Decimal("300.00")

    def test_schema_requires_multiplier_for_derived_target(self):
        with pytest.raises(ValueError, match="emergency_multiplier is required"):
            ReserveFundCreate(
                name="X",
                kind=ReserveFundKind.VACATION,
                target_amount=Decimal("0"),
                backing_account_id=1,
                target_from_spending=True,
            )

    async def test_update_rejects_derived_target_without_multiplier(self, session: AsyncSession):
        from kaleta.exceptions import ValidationError

        acc = await _make_account(session, Decimal("0"))
        fund = await _make_fund(
            session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None
        )
        with pytest.raises(ValidationError, match="emergency_multiplier is required"):
            await ReserveFundService(session).update(
                fund.id, ReserveFundUpdate(target_from_spending=True)
            )


# ── Archive ───────────────────────────────────────────────────────────────────


class TestArchive:
    async def test_archive_sets_flag_and_timestamp(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        fund = await _make_fund(session, account_id=acc)
        svc = ReserveFundService(session)
        archived = await svc.archive(fund.id)
        assert archived is not None
        assert archived.is_archived is True
        assert archived.archived_at is not None

    async def test_archive_missing_returns_none(self, session: AsyncSession):
        assert await ReserveFundService(session).archive(999) is None

    async def test_unarchive_clears_flag(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        fund = await _make_fund(session, account_id=acc)
        svc = ReserveFundService(session)
        await svc.archive(fund.id)
        restored = await svc.unarchive(fund.id)
        assert restored is not None
        assert restored.is_archived is False
        assert restored.archived_at is None

    async def test_list_hides_archived_by_default(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        fund_a = await _make_fund(session, account_id=acc, kind=ReserveFundKind.EMERGENCY)
        await _make_fund(session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None)
        svc = ReserveFundService(session)
        await svc.archive(fund_a.id)
        active = await svc.list()
        assert len(active) == 1
        assert active[0].kind == ReserveFundKind.VACATION

    async def test_list_include_archived_returns_all(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        fund_a = await _make_fund(session, account_id=acc, kind=ReserveFundKind.EMERGENCY)
        await _make_fund(session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None)
        svc = ReserveFundService(session)
        await svc.archive(fund_a.id)
        everything = await svc.list(include_archived=True)
        assert len(everything) == 2

    async def test_list_with_progress_respects_archive_flag(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("100"))
        fund_a = await _make_fund(session, account_id=acc, kind=ReserveFundKind.EMERGENCY)
        await _make_fund(session, account_id=acc, kind=ReserveFundKind.VACATION, multiplier=None)
        svc = ReserveFundService(session)
        await svc.archive(fund_a.id)
        assert len(await svc.list_with_progress()) == 1
        assert len(await svc.list_with_progress(include_archived=True)) == 2

    async def test_update_kind_reclassifies_fund(self, session: AsyncSession):
        acc = await _make_account(session, Decimal("0"))
        fund = await _make_fund(
            session, account_id=acc, kind=ReserveFundKind.IRREGULAR, multiplier=None
        )
        svc = ReserveFundService(session)
        updated = await svc.update(fund.id, ReserveFundUpdate(kind=ReserveFundKind.VACATION))
        assert updated is not None
        assert updated.kind == ReserveFundKind.VACATION


# ── The dashboard's Safety-fund-cover figure ─────────────────────────────────


def _fund(kind: ReserveFundKind, cover: str | None) -> ReserveFundWithProgress:
    """A fund carrying only what the Watch band reads off it."""
    return ReserveFundWithProgress.model_validate(
        {
            "id": 1,
            "name": "Fund",
            "kind": kind,
            "target_amount": Decimal("0.00"),
            "backing_mode": ReserveFundBackingMode.ACCOUNT,
            "backing_account_id": 1,
            "emergency_multiplier": 6,
            "current_balance": Decimal("0.00"),
            "progress_pct": Decimal("0.00"),
            "months_of_coverage": None if cover is None else Decimal(cover),
        }
    )


class TestEmergencyCover:
    def test_no_funds_at_all(self) -> None:
        assert ReserveFundService.emergency_cover([]) is None

    def test_a_fund_of_another_kind_does_not_count(self) -> None:
        assert ReserveFundService.emergency_cover([_fund(ReserveFundKind.VACATION, "4.0")]) is None

    def test_a_fund_with_nothing_to_measure_against(self) -> None:
        """No spending in the window — `with_progress` answers None, so do we."""
        assert ReserveFundService.emergency_cover([_fund(ReserveFundKind.EMERGENCY, None)]) is None

    def test_an_empty_fund_covers_zero_months_and_says_so(self) -> None:
        """Not the same as having no answer: a fund with nothing in it, on a
        ledger that has spending, covers exactly zero months."""
        assert ReserveFundService.emergency_cover(
            [_fund(ReserveFundKind.EMERGENCY, "0.0")]
        ) == Decimal("0.0")

    def test_one_fund_reads_its_own_cover(self) -> None:
        assert ReserveFundService.emergency_cover(
            [_fund(ReserveFundKind.EMERGENCY, "4.6")]
        ) == Decimal("4.6")

    def test_two_funds_cover_the_sum_of_their_months(self) -> None:
        """Both divide by the same monthly spend, so the months add up —
        answering with the first would have left the other fund out."""
        funds = [
            _fund(ReserveFundKind.EMERGENCY, "4.6"),
            _fund(ReserveFundKind.EMERGENCY, "1.4"),
        ]

        assert ReserveFundService.emergency_cover(funds) == Decimal("6.0")
