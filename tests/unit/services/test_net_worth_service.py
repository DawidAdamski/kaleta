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
from kaleta.schemas.currency_rate import CurrencyRateCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, CategoryService, NetWorthService, TransactionService
from kaleta.services.currency_rate_service import CurrencyRateService
from kaleta.services.net_worth_service import AccountSnapshot, MonthlyNetWorth, NetWorthSummary

TODAY = datetime.date.today()


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_account(
    session: AsyncSession,
    name: str = "Checking",
    balance: Decimal = Decimal("0.00"),
    account_type: AccountType = AccountType.CHECKING,
    currency: str = "PLN",
) -> int:
    svc = AccountService(session)
    acc = await svc.create(
        AccountCreate(name=name, type=account_type, balance=balance, currency=currency)
    )
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
    """Classification is kind-based: checking/savings/cash → asset, credit → liability."""

    def _snap(
        self,
        balance: Decimal,
        account_type: AccountType = AccountType.CHECKING,
    ) -> AccountSnapshot:
        # In the single-currency (PLN) case balance_in_default == balance
        return AccountSnapshot(
            id=1,
            name="Test",
            type=account_type,
            institution_name=None,
            balance=balance,
            balance_in_default=balance,
        )

    def test_is_asset_true_for_checking(self):
        snap = self._snap(Decimal("500.00"), AccountType.CHECKING)
        assert snap.is_asset is True

    def test_is_asset_true_for_savings(self):
        snap = self._snap(Decimal("500.00"), AccountType.SAVINGS)
        assert snap.is_asset is True

    def test_is_asset_true_for_cash(self):
        snap = self._snap(Decimal("500.00"), AccountType.CASH)
        assert snap.is_asset is True

    def test_is_asset_true_even_when_checking_is_overdrawn(self):
        # Kind-based classification ignores sign.
        snap = self._snap(Decimal("-100.00"), AccountType.CHECKING)
        assert snap.is_asset is True

    def test_is_asset_false_for_credit(self):
        snap = self._snap(Decimal("-100.00"), AccountType.CREDIT)
        assert snap.is_asset is False

    def test_asset_value_equals_balance_for_asset_kind(self):
        snap = self._snap(Decimal("1234.56"), AccountType.SAVINGS)
        assert snap.asset_value == Decimal("1234.56")

    def test_asset_value_zero_for_liability_kind(self):
        snap = self._snap(Decimal("-500.00"), AccountType.CREDIT)
        assert snap.asset_value == Decimal("0")

    def test_asset_value_includes_overdrawn_balance(self):
        # Overdrawn checking is still an asset-kind account; its (negative)
        # balance contributes to the assets total.
        snap = self._snap(Decimal("-50.00"), AccountType.CHECKING)
        assert snap.asset_value == Decimal("-50.00")

    def test_liability_value_is_abs_balance_for_credit(self):
        snap = self._snap(Decimal("-300.00"), AccountType.CREDIT)
        assert snap.liability_value == Decimal("300.00")

    def test_liability_value_zero_for_asset_kind(self):
        snap = self._snap(Decimal("-300.00"), AccountType.CHECKING)
        assert snap.liability_value == Decimal("0")

    def test_liability_value_zero_when_credit_balance_is_zero(self):
        snap = self._snap(Decimal("0.00"), AccountType.CREDIT)
        assert snap.liability_value == Decimal("0")


# ── NetWorthSummary aggregates ────────────────────────────────────────────────


class TestNetWorthSummaryAggregates:
    def _summary(
        self,
        accounts_spec: list[tuple[Decimal, AccountType]],
    ) -> NetWorthSummary:
        accounts = [
            AccountSnapshot(
                id=i,
                name=f"Acc{i}",
                type=t,
                institution_name=None,
                balance=b,
                balance_in_default=b,
            )
            for i, (b, t) in enumerate(accounts_spec, start=1)
        ]
        history = [MonthlyNetWorth(year=2025, month=1, net_worth=Decimal("0"))]
        return NetWorthSummary(
            accounts=accounts, physical_assets=[], history=history, prev_month_net_worth=None
        )

    def test_total_assets_sums_asset_kind_balances(self):
        # Kind-based: all asset-kind accounts contribute (including negatives).
        summary = self._summary(
            [
                (Decimal("1000.00"), AccountType.CHECKING),
                (Decimal("-200.00"), AccountType.CREDIT),
                (Decimal("500.00"), AccountType.SAVINGS),
            ]
        )
        assert summary.total_assets == Decimal("1500.00")

    def test_total_liabilities_sums_credit_balances_as_positive(self):
        summary = self._summary(
            [
                (Decimal("1000.00"), AccountType.CHECKING),
                (Decimal("-200.00"), AccountType.CREDIT),
                (Decimal("-50.00"), AccountType.CREDIT),
            ]
        )
        assert summary.total_liabilities == Decimal("250.00")

    def test_net_worth_equals_assets_minus_liabilities(self):
        summary = self._summary(
            [
                (Decimal("1000.00"), AccountType.CHECKING),
                (Decimal("-300.00"), AccountType.CREDIT),
            ]
        )
        assert summary.net_worth == Decimal("700.00")

    def test_total_liabilities_zero_when_no_credit_accounts(self):
        summary = self._summary(
            [
                (Decimal("100.00"), AccountType.CHECKING),
                (Decimal("50.00"), AccountType.SAVINGS),
            ]
        )
        assert summary.total_liabilities == Decimal("0")

    def test_net_worth_equals_balance_when_single_positive_account(self):
        summary = self._summary([(Decimal("5000.00"), AccountType.CHECKING)])
        assert summary.net_worth == Decimal("5000.00")

    def test_net_worth_negative_when_liabilities_exceed_assets(self):
        summary = self._summary(
            [
                (Decimal("200.00"), AccountType.CHECKING),
                (Decimal("-800.00"), AccountType.CREDIT),
            ]
        )
        assert summary.net_worth == Decimal("-600.00")

    def test_overdrawn_checking_counts_negatively_toward_assets(self):
        # An overdrawn asset-kind account reduces total_assets; it is not
        # reclassified as a liability.
        summary = self._summary(
            [
                (Decimal("-100.00"), AccountType.CHECKING),
                (Decimal("-50.00"), AccountType.CHECKING),
            ]
        )
        assert summary.total_assets == Decimal("-150.00")
        assert summary.total_liabilities == Decimal("0")

    def test_monthly_change_none_when_prev_month_is_none(self):
        summary = self._summary([(Decimal("500.00"), AccountType.CHECKING)])
        assert summary.monthly_change is None

    def test_monthly_change_positive(self):
        accounts = [
            AccountSnapshot(
                id=1,
                name="A",
                type=AccountType.CHECKING,
                institution_name=None,
                balance=Decimal("1200.00"),
                balance_in_default=Decimal("1200.00"),
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
                balance_in_default=Decimal("800.00"),
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

    async def test_total_assets_reflects_asset_kind_accounts(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Savings", balance=Decimal("5000.00"))
        await _make_account(
            session, name="Credit", balance=Decimal("-1000.00"), account_type=AccountType.CREDIT
        )
        summary = await svc.get_summary()
        assert summary.total_assets == Decimal("5000.00")

    async def test_total_liabilities_reflects_credit_accounts(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Savings", balance=Decimal("5000.00"))
        await _make_account(
            session, name="Credit", balance=Decimal("-1000.00"), account_type=AccountType.CREDIT
        )
        summary = await svc.get_summary()
        assert summary.total_liabilities == Decimal("1000.00")

    async def test_net_worth_assets_minus_liabilities(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Savings", balance=Decimal("5000.00"))
        await _make_account(
            session, name="Credit", balance=Decimal("-1000.00"), account_type=AccountType.CREDIT
        )
        summary = await svc.get_summary()
        assert summary.net_worth == Decimal("4000.00")

    async def test_all_history_entries_same_net_worth_when_no_transactions(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Checking", balance=Decimal("2000.00"))
        summary = await svc.get_summary(history_months=13)
        # No transactions means all history entries should equal current net worth.
        for entry in summary.history:
            assert entry.net_worth == summary.net_worth

    async def test_monthly_change_zero_when_no_transactions(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Checking", balance=Decimal("3000.00"))
        summary = await svc.get_summary(history_months=13)
        assert summary.monthly_change == Decimal("0")

    async def test_zero_balance_account_contributes_nothing(
        self, svc: NetWorthService, session: AsyncSession
    ):
        # A zero-balance checking still sits in the assets column (kind-based),
        # but contributes 0 to the total.
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


# ── AccountSnapshot currency & balance_in_default ────────────────────────────


class TestAccountSnapshotCurrency:
    def _snap(
        self, balance: Decimal, currency: str = "PLN", balance_in_default: Decimal | None = None
    ) -> AccountSnapshot:  # noqa: E501
        return AccountSnapshot(
            id=1,
            name="Test",
            type=AccountType.CHECKING,
            institution_name=None,
            balance=balance,
            currency=currency,
            balance_in_default=balance_in_default if balance_in_default is not None else balance,
        )

    def test_currency_field_stored(self):
        snap = self._snap(Decimal("100.00"), currency="EUR")
        assert snap.currency == "EUR"

    def test_balance_in_default_computed_correctly(self):
        # 100 EUR * 4.25 = 425 PLN
        snap = self._snap(Decimal("100.00"), currency="EUR", balance_in_default=Decimal("425.00"))
        assert snap.balance_in_default == Decimal("425.00")

    def test_is_asset_by_kind_regardless_of_currency(self):
        # Kind-based classification ignores balance sign/currency — a CHECKING
        # account is always an asset.
        snap = AccountSnapshot(
            id=1,
            name="Test",
            type=AccountType.CHECKING,
            institution_name=None,
            balance=Decimal("-50.00"),
            currency="EUR",
            balance_in_default=Decimal("100.00"),
        )
        assert snap.is_asset is True

    def test_is_asset_false_for_credit_kind(self):
        snap = AccountSnapshot(
            id=1,
            name="Credit EUR",
            type=AccountType.CREDIT,
            institution_name=None,
            balance=Decimal("-100.00"),
            currency="EUR",
            balance_in_default=Decimal("-425.00"),
        )
        assert snap.is_asset is False

    def test_asset_value_uses_balance_in_default(self):
        snap = self._snap(Decimal("200.00"), currency="USD", balance_in_default=Decimal("760.00"))
        assert snap.asset_value == Decimal("760.00")

    def test_liability_value_uses_balance_in_default(self):
        snap = AccountSnapshot(
            id=1,
            name="Credit EUR",
            type=AccountType.CREDIT,
            institution_name=None,
            balance=Decimal("-100.00"),
            currency="EUR",
            balance_in_default=Decimal("-425.00"),
        )
        assert snap.liability_value == Decimal("425.00")


# ── get_summary() — multi-currency rate conversion ────────────────────────────


async def _add_rate(
    session: AsyncSession,
    from_currency: str,
    to_currency: str,
    rate: Decimal,
    on_date: datetime.date | None = None,
) -> None:
    svc = CurrencyRateService(session)
    await svc.create(
        CurrencyRateCreate(
            date=on_date or TODAY,
            from_currency=from_currency,
            to_currency=to_currency,
            rate=rate,
        )
    )


class TestGetSummaryMultiCurrency:
    async def test_eur_account_converted_via_rate(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Euro Acc", balance=Decimal("100.00"), currency="EUR")
        await _add_rate(session, "EUR", "PLN", Decimal("4.25"))
        summary = await svc.get_summary(default_currency="PLN")
        snap = summary.accounts[0]
        assert snap.currency == "EUR"
        assert snap.balance_in_default == Decimal("425.00")

    async def test_pln_account_with_default_pln_unchanged(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="PLN Acc", balance=Decimal("1000.00"), currency="PLN")
        summary = await svc.get_summary(default_currency="PLN")
        snap = summary.accounts[0]
        assert snap.balance_in_default == Decimal("1000.00")

    async def test_total_assets_sums_balance_in_default(
        self, svc: NetWorthService, session: AsyncSession
    ):
        # 100 EUR @ 4.25 = 425 PLN, 200 PLN = 200 PLN → total = 625 PLN
        await _make_account(session, name="Euro Acc", balance=Decimal("100.00"), currency="EUR")
        await _make_account(session, name="PLN Acc", balance=Decimal("200.00"), currency="PLN")
        await _add_rate(session, "EUR", "PLN", Decimal("4.25"))
        summary = await svc.get_summary(default_currency="PLN")
        assert summary.total_assets == Decimal("625.00")

    async def test_unknown_currency_falls_back_to_1_to_1(
        self, svc: NetWorthService, session: AsyncSession
    ):
        """When no rate is in the DB for a currency, falls back to 1:1 — no crash."""
        await _make_account(session, name="CHF Acc", balance=Decimal("50.00"), currency="CHF")
        # No CHF rate in DB
        summary = await svc.get_summary(default_currency="PLN")
        snap = summary.accounts[0]
        assert snap.balance_in_default == Decimal("50.00")
        assert snap.rate_known is False

    async def test_no_foreign_accounts_no_crash(self, svc: NetWorthService, session: AsyncSession):
        """No foreign currency accounts — get_summary() must not raise."""
        await _make_account(session, name="PLN Acc", balance=Decimal("100.00"), currency="PLN")
        summary = await svc.get_summary()
        assert summary.accounts[0].balance_in_default == Decimal("100.00")

    async def test_net_worth_uses_converted_balances(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Euro Asset", balance=Decimal("200.00"), currency="EUR")
        await _make_account(
            session,
            name="Euro Credit",
            balance=Decimal("-50.00"),
            currency="EUR",
            account_type=AccountType.CREDIT,
        )
        await _add_rate(session, "EUR", "PLN", Decimal("4.00"))
        summary = await svc.get_summary(default_currency="PLN")
        # assets: 200 * 4 = 800, liabilities: 50 * 4 = 200, net = 600
        assert summary.total_assets == Decimal("800.00")
        assert summary.total_liabilities == Decimal("200.00")
        assert summary.net_worth == Decimal("600.00")

    async def test_default_currency_in_summary(self, svc: NetWorthService, session: AsyncSession):
        summary = await svc.get_summary(default_currency="EUR")
        assert summary.default_currency == "EUR"

    async def test_pln_account_is_default_currency(
        self, svc: NetWorthService, session: AsyncSession
    ):
        """PLN account with default_currency=PLN needs no rate entry in DB."""
        await _make_account(session, name="PLN Acc", balance=Decimal("500.00"), currency="PLN")
        summary = await svc.get_summary(default_currency="PLN")
        snap = summary.accounts[0]
        assert snap.balance_in_default == Decimal("500.00")
        assert snap.rate_known is True

    async def test_inverse_rate_used_when_direct_missing(
        self, svc: NetWorthService, session: AsyncSession
    ):
        """If EUR→PLN is missing but PLN→EUR exists, service uses the inverse."""
        await _make_account(session, name="Euro Acc", balance=Decimal("100.00"), currency="EUR")
        # Store PLN→EUR (inverse); service should find EUR→PLN = 1/0.235... ≈ 4.25
        await _add_rate(session, "PLN", "EUR", Decimal("1") / Decimal("4.25"))
        summary = await svc.get_summary(default_currency="PLN")
        snap = summary.accounts[0]
        assert abs(snap.balance_in_default - Decimal("425.00")) < Decimal("0.01")


# ── Deltas (30d, YTD) and per-month asset/liability split ────────────────────


class TestDeltas:
    async def test_delta_30d_none_when_history_has_one_entry(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, balance=Decimal("1000.00"))
        summary = await svc.get_summary(history_months=1)
        assert summary.delta_30d is None

    async def test_delta_30d_zero_when_no_transactions(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, balance=Decimal("1000.00"))
        summary = await svc.get_summary(history_months=2)
        assert summary.delta_30d == Decimal("0")

    async def test_delta_30d_reflects_current_month_income(
        self, svc: NetWorthService, session: AsyncSession
    ):
        acc_id = await _make_account(session, balance=Decimal("1500.00"))
        cat_id = await _make_category(session)
        await _make_transaction(
            session, acc_id, cat_id, Decimal("500.00"), TransactionType.INCOME, date=TODAY
        )
        summary = await svc.get_summary(history_months=2)
        # current = 1500, history[-2] = 1000, delta = +500
        assert summary.delta_30d == Decimal("500.00")

    async def test_delta_ytd_none_when_only_current_month_in_history(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, balance=Decimal("1000.00"))
        summary = await svc.get_summary(history_months=1)
        assert summary.delta_ytd is None

    async def test_delta_ytd_computes_from_january_baseline(
        self, svc: NetWorthService, session: AsyncSession
    ):
        """YTD delta uses the first history entry in the current year as baseline."""
        await _make_account(session, balance=Decimal("2000.00"))
        # 13 months of history covers last Jan through this month; history[0]
        # will typically be prior year, and there WILL be a Jan-of-this-year entry.
        summary = await svc.get_summary(history_months=13)
        # With no transactions, net worth is constant → YTD delta = 0.
        assert summary.delta_ytd == Decimal("0")


class TestMonthlySplit:
    async def test_monthly_history_includes_total_assets_and_liabilities(
        self, svc: NetWorthService, session: AsyncSession
    ):
        await _make_account(session, name="Checking", balance=Decimal("3000.00"))
        await _make_account(
            session, name="Card", balance=Decimal("-500.00"), account_type=AccountType.CREDIT
        )
        summary = await svc.get_summary(history_months=3)
        for entry in summary.history:
            # With no transactions, assets/liabilities are constant.
            assert entry.total_assets == Decimal("3000.00")
            assert entry.total_liabilities == Decimal("500.00")
            assert entry.net_worth == Decimal("2500.00")

    async def test_monthly_history_rolls_back_per_account(
        self, svc: NetWorthService, session: AsyncSession
    ):
        """Income on the checking side raises current assets; history[-2] shows pre-income state."""
        acc_id = await _make_account(session, balance=Decimal("1500.00"))
        cat_id = await _make_category(session)
        await _make_transaction(
            session, acc_id, cat_id, Decimal("500.00"), TransactionType.INCOME, date=TODAY
        )
        summary = await svc.get_summary(history_months=2)
        assert summary.history[-1].total_assets == Decimal("1500.00")
        assert summary.history[-2].total_assets == Decimal("1000.00")

    async def test_monthly_history_liabilities_tracked_separately(
        self, svc: NetWorthService, session: AsyncSession
    ):
        """Payments against a credit card should not inflate the assets line."""
        credit_id = await _make_account(
            session, balance=Decimal("-200.00"), account_type=AccountType.CREDIT, name="Card"
        )
        cat_id = await _make_category(session, cat_type=CategoryType.EXPENSE)
        # Add an expense on the credit card this month → balance was worse in the past.
        # Amount=300 expense means account was +300 last month → -500 before the expense.
        await _make_transaction(
            session, credit_id, cat_id, Decimal("300.00"), TransactionType.EXPENSE, date=TODAY
        )
        summary = await svc.get_summary(history_months=2)
        # Current: -200 balance → liabilities 200. Prior month: -200 + 300 = +100
        # balance, so liabilities were -100 (i.e. the card was in credit). The
        # liability_value is -balance, so it's -100 historically.
        assert summary.history[-1].total_liabilities == Decimal("200.00")
        assert summary.history[-2].total_liabilities == Decimal("-100.00")
