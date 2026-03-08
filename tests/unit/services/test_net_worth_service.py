"""Unit tests for NetWorthService — uses in-memory SQLite."""

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
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, CategoryService, NetWorthService, TransactionService
from kaleta.services.net_worth_service import AccountSnapshot, MonthlyNetWorth, NetWorthSummary

TODAY = datetime.date.today()


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_account(
    session: AsyncSession,
    name: str = "Checking",
    balance: Decimal = Decimal("0.00"),
    account_type: AccountType = AccountType.CHECKING,
) -> int:
    svc = AccountService(session)
    acc = await svc.create(AccountCreate(name=name, type=account_type, balance=balance))
    return acc.id


async def _make_category(
    session: AsyncSession,
    name: str = "Salary",
    cat_type: CategoryType = CategoryType.INCOME,
) -> int:
    svc = CategoryService(session)
    cat = await svc.create(CategoryCreate(name=name, type=cat_type))
    return cat.id


async def _make_transaction(
    session: AsyncSession,
    account_id: int,
    category_id: int,
    amount: Decimal,
    tx_type: TransactionType,
    date: datetime.date = TODAY,
    is_internal_transfer: bool = False,
) -> None:
    svc = TransactionService(session)
    tx_type_arg = tx_type
    if is_internal_transfer:
        tx_type_arg = TransactionType.TRANSFER
    await svc.create(
        TransactionCreate(
            account_id=account_id,
            category_id=None if is_internal_transfer else category_id,
            amount=amount,
            type=tx_type_arg,
            date=date,
            description="",
            is_internal_transfer=is_internal_transfer,
        )
    )


@pytest.fixture
def svc(session: AsyncSession) -> NetWorthService:
    return NetWorthService(session)


# ── AccountSnapshot properties ────────────────────────────────────────────────


class TestAccountSnapshotProperties:

    def _snap(self, balance: Decimal) -> AccountSnapshot:
        return AccountSnapshot(
            id=1,
            name="Test",
            type=AccountType.CHECKING,
            institution_name=None,
            balance=balance,
        )

    def test_is_asset_true_for_positive_balance(self):
        snap = self._snap(Decimal("500.00"))
        assert snap.is_asset is True

    def test_is_asset_true_for_zero_balance(self):
        snap = self._snap(Decimal("0.00"))
        assert snap.is_asset is True

    def test_is_asset_false_for_negative_balance(self):
        snap = self._snap(Decimal("-100.00"))
        assert snap.is_asset is False

    def test_asset_value_equals_balance_when_positive(self):
        snap = self._snap(Decimal("1234.56"))
        assert snap.asset_value == Decimal("1234.56")

    def test_asset_value_is_zero_when_negative(self):
        snap = self._snap(Decimal("-50.00"))
        assert snap.asset_value == Decimal("0")

    def test_asset_value_is_zero_when_balance_is_zero(self):
        snap = self._snap(Decimal("0.00"))
        assert snap.asset_value == Decimal("0")

    def test_liability_value_is_abs_balance_when_negative(self):
        snap = self._snap(Decimal("-300.00"))
        assert snap.liability_value == Decimal("300.00")

    def test_liability_value_is_zero_when_positive(self):
        snap = self._snap(Decimal("200.00"))
        assert snap.liability_value == Decimal("0")

    def test_liability_value_is_zero_when_balance_is_zero(self):
        snap = self._snap(Decimal("0.00"))
        assert snap.liability_value == Decimal("0")


# ── NetWorthSummary aggregates ────────────────────────────────────────────────


class TestNetWorthSummaryAggregates:

    def _summary(self, balances: list[Decimal]) -> NetWorthSummary:
        accounts = [
            AccountSnapshot(
                id=i,
                name=f"Acc{i}",
                type=AccountType.CHECKING,
                institution_name=None,
                balance=b,
            )
            for i, b in enumerate(balances, start=1)
        ]
        history = [MonthlyNetWorth(year=2025, month=1, net_worth=Decimal("0"))]
        return NetWorthSummary(
            accounts=accounts, physical_assets=[], history=history, prev_month_net_worth=None
        )

    def test_total_assets_sums_only_positive(self):
        summary = self._summary([Decimal("1000.00"), Decimal("-200.00"), Decimal("500.00")])
        assert summary.total_assets == Decimal("1500.00")

    def test_total_liabilities_sums_abs_of_negatives(self):
        summary = self._summary([Decimal("1000.00"), Decimal("-200.00"), Decimal("-50.00")])
        assert summary.total_liabilities == Decimal("250.00")

    def test_net_worth_equals_assets_minus_liabilities(self):
        summary = self._summary([Decimal("1000.00"), Decimal("-300.00")])
        assert summary.net_worth == Decimal("700.00")

    def test_total_assets_zero_when_all_negative(self):
        summary = self._summary([Decimal("-100.00"), Decimal("-50.00")])
        assert summary.total_assets == Decimal("0")

    def test_total_liabilities_zero_when_all_positive(self):
        summary = self._summary([Decimal("100.00"), Decimal("50.00")])
        assert summary.total_liabilities == Decimal("0")

    def test_net_worth_equals_balance_when_single_positive_account(self):
        summary = self._summary([Decimal("5000.00")])
        assert summary.net_worth == Decimal("5000.00")

    def test_net_worth_negative_when_liabilities_exceed_assets(self):
        summary = self._summary([Decimal("200.00"), Decimal("-800.00")])
        assert summary.net_worth == Decimal("-600.00")

    def test_monthly_change_none_when_prev_month_is_none(self):
        summary = self._summary([Decimal("500.00")])
        assert summary.monthly_change is None

    def test_monthly_change_positive(self):
        accounts = [
            AccountSnapshot(
                id=1,
                name="A",
                type=AccountType.CHECKING,
                institution_name=None,
                balance=Decimal("1200.00"),
            )
        ]
        history = [MonthlyNetWorth(year=2025, month=1, net_worth=Decimal("1000.00"))]
        summary = NetWorthSummary(
            accounts=accounts,
            physical_assets=[],
            history=history,
            prev_month_net_worth=Decimal("1000.00"),
        )
        assert summary.monthly_change == Decimal("200.00")

    def test_monthly_change_negative(self):
        accounts = [
            AccountSnapshot(
                id=1,
                name="A",
                type=AccountType.CHECKING,
                institution_name=None,
                balance=Decimal("800.00"),
            )
        ]
        history = [MonthlyNetWorth(year=2025, month=1, net_worth=Decimal("1000.00"))]
        summary = NetWorthSummary(
            accounts=accounts,
            physical_assets=[],
            history=history,
            prev_month_net_worth=Decimal("1000.00"),
        )
        assert summary.monthly_change == Decimal("-200.00")


# ── MonthlyNetWorth.label ─────────────────────────────────────────────────────


class TestMonthlyNetWorthLabel:

    def test_label_january_2025(self):
        m = MonthlyNetWorth(year=2025, month=1, net_worth=Decimal("0"))
        assert m.label == "Jan 2025"

    def test_label_december_2024(self):
        m = MonthlyNetWorth(year=2024, month=12, net_worth=Decimal("0"))
        assert m.label == "Dec 2024"

    def test_label_june(self):
        m = MonthlyNetWorth(year=2023, month=6, net_worth=Decimal("0"))
        assert m.label == "Jun 2023"

    def test_label_format_matches_strftime(self):
        m = MonthlyNetWorth(year=2026, month=3, net_worth=Decimal("500.00"))
        expected = datetime.date(2026, 3, 1).strftime("%b %Y")
        assert m.label == expected


# ── get_summary() — no accounts ───────────────────────────────────────────────


class TestGetSummaryNoAccounts:

    async def test_empty_accounts_list(self, svc: NetWorthService):
        summary = await svc.get_summary()
        assert summary.accounts == []

    async def test_net_worth_is_zero_with_no_accounts(self, svc: NetWorthService):
        summary = await svc.get_summary()
        assert summary.net_worth == Decimal("0")

    async def test_total_assets_zero_with_no_accounts(self, svc: NetWorthService):
        summary = await svc.get_summary()
        assert summary.total_assets == Decimal("0")

    async def test_total_liabilities_zero_with_no_accounts(self, svc: NetWorthService):
        summary = await svc.get_summary()
        assert summary.total_liabilities == Decimal("0")

    async def test_history_has_correct_number_of_entries_default(self, svc: NetWorthService):
        summary = await svc.get_summary()
        assert len(summary.history) == 13

    async def test_history_custom_months(self, svc: NetWorthService):
        summary = await svc.get_summary(history_months=6)
        assert len(summary.history) == 6

    async def test_history_single_month(self, svc: NetWorthService):
        summary = await svc.get_summary(history_months=1)
        assert len(summary.history) == 1

    async def test_history_ordered_oldest_to_newest(self, svc: NetWorthService):
        summary = await svc.get_summary(history_months=3)
        years_months = [(e.year, e.month) for e in summary.history]
        assert years_months == sorted(years_months)

    async def test_history_last_entry_is_current_month(self, svc: NetWorthService):
        summary = await svc.get_summary()
        last = summary.history[-1]
        assert last.year == TODAY.year
        assert last.month == TODAY.month

    async def test_monthly_change_none_when_history_months_is_1(self, svc: NetWorthService):
        summary = await svc.get_summary(history_months=1)
        assert summary.monthly_change is None


# ── get_summary() — accounts only, no transactions ────────────────────────────


class TestGetSummaryAccountsOnly:

    async def test_accounts_sorted_by_name(self, svc: NetWorthService, session: AsyncSession):
        await _make_account(session, name="Zebra", balance=Decimal("100.00"))
        await _make_account(session, name="Apple", balance=Decimal("200.00"))
        await _make_account(session, name="Mango", balance=Decimal("300.00"))
        summary = await svc.get_summary()
        names = [a.name for a in summary.accounts]
        assert names == sorted(names)

    async def test_total_assets_reflects_positive_balances(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Savings", balance=Decimal("5000.00"))
        await _make_account(session, name="Credit", balance=Decimal("-1000.00"))
        summary = await svc.get_summary()
        assert summary.total_assets == Decimal("5000.00")

    async def test_total_liabilities_reflects_negative_balances(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Savings", balance=Decimal("5000.00"))
        await _make_account(session, name="Credit", balance=Decimal("-1000.00"))
        summary = await svc.get_summary()
        assert summary.total_liabilities == Decimal("1000.00")

    async def test_net_worth_assets_minus_liabilities(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Savings", balance=Decimal("5000.00"))
        await _make_account(session, name="Credit", balance=Decimal("-1000.00"))
        summary = await svc.get_summary()
        assert summary.net_worth == Decimal("4000.00")

    async def test_all_history_entries_same_net_worth_when_no_transactions(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Checking", balance=Decimal("2000.00"))
        summary = await svc.get_summary(history_months=13)
        # No transactions means no monthly changes; all history entries should equal current net worth
        for entry in summary.history:
            assert entry.net_worth == summary.net_worth

    async def test_monthly_change_zero_when_no_transactions(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Checking", balance=Decimal("3000.00"))
        summary = await svc.get_summary(history_months=13)
        assert summary.monthly_change == Decimal("0")

    async def test_zero_balance_accounts_not_counted_as_asset_or_liability(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Empty", balance=Decimal("0.00"))
        summary = await svc.get_summary()
        assert summary.total_assets == Decimal("0")
        assert summary.total_liabilities == Decimal("0")
        assert summary.net_worth == Decimal("0")


# ── get_summary() — with transactions ─────────────────────────────────────────


class TestGetSummaryWithTransactions:

    async def test_income_in_current_month_reflected_in_last_history_entry(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, name="Checking", balance=Decimal("1500.00"))
        cat_id = await _make_category(session, name="Salary", cat_type=CategoryType.INCOME)
        # Income of 500 this month — net worth is 1500, so prior month net worth = 1500 - 500 = 1000
        await _make_transaction(
            session, acc_id, cat_id, Decimal("500.00"), TransactionType.INCOME, date=TODAY
        )
        summary = await svc.get_summary(history_months=2)
        assert summary.history[-1].net_worth == Decimal("1500.00")
        assert summary.history[-2].net_worth == Decimal("1000.00")

    async def test_expense_in_current_month_reflected_in_last_history_entry(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, name="Checking", balance=Decimal("800.00"))
        cat_id = await _make_category(session, name="Food", cat_type=CategoryType.EXPENSE)
        # Expense of 200 this month — prior month net worth = 800 + 200 = 1000
        await _make_transaction(
            session, acc_id, cat_id, Decimal("200.00"), TransactionType.EXPENSE, date=TODAY
        )
        summary = await svc.get_summary(history_months=2)
        assert summary.history[-1].net_worth == Decimal("800.00")
        assert summary.history[-2].net_worth == Decimal("1000.00")

    async def test_monthly_change_positive_when_income_exceeds_expenses(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, name="Checking", balance=Decimal("2000.00"))
        inc_cat_id = await _make_category(session, name="Salary", cat_type=CategoryType.INCOME)
        exp_cat_id = await _make_category(session, name="Food", cat_type=CategoryType.EXPENSE)
        # Net this month: +1000 income, -300 expense = +700
        await _make_transaction(
            session, acc_id, inc_cat_id, Decimal("1000.00"), TransactionType.INCOME, date=TODAY
        )
        await _make_transaction(
            session, acc_id, exp_cat_id, Decimal("300.00"), TransactionType.EXPENSE, date=TODAY
        )
        summary = await svc.get_summary(history_months=2)
        assert summary.monthly_change == Decimal("700.00")

    async def test_monthly_change_negative_when_expenses_exceed_income(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, name="Checking", balance=Decimal("500.00"))
        inc_cat_id = await _make_category(session, name="Salary", cat_type=CategoryType.INCOME)
        exp_cat_id = await _make_category(session, name="Food", cat_type=CategoryType.EXPENSE)
        # Net this month: +100 income, -600 expense = -500
        await _make_transaction(
            session, acc_id, inc_cat_id, Decimal("100.00"), TransactionType.INCOME, date=TODAY
        )
        await _make_transaction(
            session, acc_id, exp_cat_id, Decimal("600.00"), TransactionType.EXPENSE, date=TODAY
        )
        summary = await svc.get_summary(history_months=2)
        assert summary.monthly_change == Decimal("-500.00")

    async def test_transaction_in_prior_month_affects_correct_history_slot(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, name="Checking", balance=Decimal("1000.00"))
        cat_id = await _make_category(session, name="Salary", cat_type=CategoryType.INCOME)
        # Compute the month that will land in history[-2] (one month ago) by arithmetic
        total_months = TODAY.year * 12 + TODAY.month - 1
        last_month_total = total_months - 1
        last_month_year, last_month_month = last_month_total // 12, last_month_total % 12 + 1
        last_month_date = datetime.date(last_month_year, last_month_month, 15)
        # Income of 400 placed in the previous calendar month
        await _make_transaction(
            session, acc_id, cat_id, Decimal("400.00"), TransactionType.INCOME, date=last_month_date
        )
        summary = await svc.get_summary(history_months=3)
        # history[-1] = current month (1000, no tx here)
        # history[-2] = last month — has the 400 income, so the entry records net_worth BEFORE
        #               subtracting it; running starts at 1000, so history[-2] = 1000 still
        # After subtracting 400: running = 600
        # history[-3] = two months ago = 600
        assert summary.history[-1].net_worth == Decimal("1000.00")
        assert summary.history[-2].net_worth == Decimal("1000.00")
        assert summary.history[-3].net_worth == Decimal("600.00")

    async def test_history_months_1_monthly_change_is_none(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, name="Checking", balance=Decimal("500.00"))
        cat_id = await _make_category(session, name="Salary", cat_type=CategoryType.INCOME)
        await _make_transaction(
            session, acc_id, cat_id, Decimal("200.00"), TransactionType.INCOME, date=TODAY
        )
        summary = await svc.get_summary(history_months=1)
        assert summary.monthly_change is None

    async def test_history_months_2_gives_monthly_change(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, name="Checking", balance=Decimal("1200.00"))
        cat_id = await _make_category(session, name="Salary", cat_type=CategoryType.INCOME)
        await _make_transaction(
            session, acc_id, cat_id, Decimal("200.00"), TransactionType.INCOME, date=TODAY
        )
        summary = await svc.get_summary(history_months=2)
        assert summary.monthly_change is not None
        assert summary.monthly_change == Decimal("200.00")


# ── Internal transfers excluded ───────────────────────────────────────────────


class TestInternalTransfersExcluded:

    async def test_internal_transfer_does_not_affect_history(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, name="Checking", balance=Decimal("1000.00"))
        cat_id = await _make_category(session, name="Salary", cat_type=CategoryType.INCOME)
        # Create an internal transfer — should not affect monthly_net calculation
        await _make_transaction(
            session,
            acc_id,
            cat_id,
            Decimal("500.00"),
            TransactionType.TRANSFER,
            date=TODAY,
            is_internal_transfer=True,
        )
        summary = await svc.get_summary(history_months=2)
        # No net change from transfers — both months should equal current net worth
        assert summary.history[-1].net_worth == Decimal("1000.00")
        assert summary.history[-2].net_worth == Decimal("1000.00")
        assert summary.monthly_change == Decimal("0")

    async def test_internal_transfer_mixed_with_real_income(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, name="Checking", balance=Decimal("1300.00"))
        inc_cat_id = await _make_category(session, name="Salary", cat_type=CategoryType.INCOME)
        # Real income of 300 this month
        await _make_transaction(
            session, acc_id, inc_cat_id, Decimal("300.00"), TransactionType.INCOME, date=TODAY
        )
        # Internal transfer — should not contribute
        await _make_transaction(
            session,
            acc_id,
            inc_cat_id,
            Decimal("500.00"),
            TransactionType.TRANSFER,
            date=TODAY,
            is_internal_transfer=True,
        )
        summary = await svc.get_summary(history_months=2)
        # Only the 300 income should be counted
        assert summary.monthly_change == Decimal("300.00")


# ── account snapshot institution_name ────────────────────────────────────────


class TestAccountSnapshotInstitutionName:

    async def test_institution_name_is_none_without_institution(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Lone Account", balance=Decimal("100.00"))
        summary = await svc.get_summary()
        assert summary.accounts[0].institution_name is None
