"""Unit tests for WizardProjectionService."""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.reserve_fund import ReserveFundBackingMode, ReserveFundKind
from kaleta.models.subscription import SubscriptionStatus
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.credit import LoanProfileCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.reserve_fund import ReserveFundCreate
from kaleta.schemas.subscription import SubscriptionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    CreditService,
    PlannedTransactionService,
    ReserveFundService,
    SubscriptionService,
    WizardProjectionService,
)
from kaleta.services.wizard_projection_service import (
    _monthly_from_planned,
    _monthly_from_reserve,
    _monthly_from_subscription,
)


async def _make_account(
    session: AsyncSession, name: str, type_: AccountType = AccountType.CHECKING
) -> int:
    a = await AccountService(session).create(
        AccountCreate(name=name, type=type_, balance=Decimal("0"))
    )
    return a.id


async def _make_category(session: AsyncSession, name: str, ttype: CategoryType) -> int:
    c = await CategoryService(session).create(CategoryCreate(name=name, type=ttype))
    return c.id


# ── Pure helpers ─────────────────────────────────────────────────────────────


class TestMonthlyHelpers:
    def test_monthly_from_subscription_monthly(self):
        from kaleta.models.subscription import Subscription

        sub = Subscription(
            name="Netflix", amount=Decimal("49.99"), cadence_days=30
        )
        assert _monthly_from_subscription(sub) == Decimal("49.99")

    def test_monthly_from_subscription_yearly(self):
        from kaleta.models.subscription import Subscription

        sub = Subscription(
            name="Amazon Prime", amount=Decimal("365.00"), cadence_days=365
        )
        # 365 × 30 / 365 = 30/mo.
        assert _monthly_from_subscription(sub) == Decimal("30.00")

    def test_monthly_from_planned_yearly(self):
        from kaleta.models.planned_transaction import PlannedTransaction

        pt = PlannedTransaction(
            name="Insurance",
            account_id=1,
            amount=Decimal("1200"),
            type=TransactionType.EXPENSE,
            frequency=RecurrenceFrequency.YEARLY,
            interval=1,
            start_date=datetime.date(2026, 1, 1),
        )
        assert _monthly_from_planned(pt) == Decimal("100.00")

    def test_monthly_from_planned_biweekly_interval_2(self):
        from kaleta.models.planned_transaction import PlannedTransaction

        pt = PlannedTransaction(
            name="Gym",
            account_id=1,
            amount=Decimal("60"),
            type=TransactionType.EXPENSE,
            frequency=RecurrenceFrequency.BIWEEKLY,
            interval=2,
            start_date=datetime.date(2026, 1, 1),
        )
        # 60 × (30/14) / 2 ≈ 60 × 2.14 / 2 ≈ 64.29
        assert _monthly_from_planned(pt) == Decimal("64.29")

    def test_monthly_from_planned_once_returns_zero(self):
        from kaleta.models.planned_transaction import PlannedTransaction

        pt = PlannedTransaction(
            name="Big Purchase",
            account_id=1,
            amount=Decimal("500"),
            type=TransactionType.EXPENSE,
            frequency=RecurrenceFrequency.ONCE,
            interval=1,
            start_date=datetime.date(2026, 5, 1),
        )
        assert _monthly_from_planned(pt) == Decimal("0")

    def test_monthly_from_reserve_emergency_uses_multiplier(self):
        from kaleta.models.reserve_fund import ReserveFund

        fund = ReserveFund(
            name="Emergency",
            kind=ReserveFundKind.EMERGENCY,
            target_amount=Decimal("60000"),
            emergency_multiplier=6,
            backing_mode=ReserveFundBackingMode.ACCOUNT,
        )
        # 60000 / 6 = 10000/mo (plan's "one month of survival per month").
        assert _monthly_from_reserve(fund) == Decimal("10000.00")

    def test_monthly_from_reserve_vacation_uses_twelfth(self):
        from kaleta.models.reserve_fund import ReserveFund

        fund = ReserveFund(
            name="Vacation",
            kind=ReserveFundKind.VACATION,
            target_amount=Decimal("12000"),
            backing_mode=ReserveFundBackingMode.ACCOUNT,
        )
        assert _monthly_from_reserve(fund) == Decimal("1000.00")


# ── Budget Builder projection ────────────────────────────────────────────────


class TestBudgetBuilderProjection:
    async def test_empty_db_returns_empty_projection(self, session: AsyncSession):
        svc = WizardProjectionService(session)
        result = await svc.get_budget_builder_sources(2026)
        assert result.income == []
        assert result.fixed == []
        assert result.reserves == []

    async def test_planned_income_lands_in_income(
        self, session: AsyncSession
    ):
        acc = await _make_account(session, "Main")
        await PlannedTransactionService(session).create(
            PlannedTransactionCreate(
                name="Salary",
                account_id=acc,
                amount=Decimal("8000"),
                type=TransactionType.INCOME,
                frequency=RecurrenceFrequency.MONTHLY,
                interval=1,
                start_date=datetime.date(2026, 1, 1),
                is_active=True,
            )
        )
        result = await WizardProjectionService(session).get_budget_builder_sources(2026)
        assert len(result.income) == 1
        assert result.income[0].amount == Decimal("8000.00")
        assert result.income[0].source_kind == "planned"

    async def test_subscription_lands_in_fixed(self, session: AsyncSession):
        svc = SubscriptionService(session)
        await svc.create(
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("49.99"),
                cadence_days=30,
            )
        )
        result = await WizardProjectionService(session).get_budget_builder_sources(2026)
        assert len(result.fixed) == 1
        assert result.fixed[0].source_kind == "subscription"
        assert result.fixed[0].amount == Decimal("49.99")

    async def test_yearly_subscription_amortised_to_monthly(
        self, session: AsyncSession
    ):
        await SubscriptionService(session).create(
            SubscriptionCreate(
                name="Amazon Prime",
                amount=Decimal("365"),
                cadence_days=365,
            )
        )
        result = await WizardProjectionService(session).get_budget_builder_sources(2026)
        assert result.fixed[0].amount == Decimal("30.00")
        assert result.fixed[0].cadence == "yearly"

    async def test_reserves_projected(self, session: AsyncSession):
        acc = await _make_account(session, "Savings", AccountType.SAVINGS)
        await ReserveFundService(session).create(
            ReserveFundCreate(
                name="Emergency",
                kind=ReserveFundKind.EMERGENCY,
                target_amount=Decimal("60000"),
                backing_mode=ReserveFundBackingMode.ACCOUNT,
                backing_account_id=acc,
                emergency_multiplier=6,
            )
        )
        result = await WizardProjectionService(session).get_budget_builder_sources(2026)
        assert len(result.reserves) == 1
        assert result.reserves[0].amount == Decimal("10000.00")

    async def test_loan_monthly_payment_in_fixed(self, session: AsyncSession):
        acc = await _make_account(session, "Car loan", AccountType.CREDIT)
        await CreditService(session).create_loan(
            LoanProfileCreate(
                account_id=acc,
                principal=Decimal("12000"),
                apr=Decimal("0"),
                term_months=12,
                start_date=datetime.date(2026, 1, 1),
            )
        )
        result = await WizardProjectionService(session).get_budget_builder_sources(2026)
        loan_rows = [r for r in result.fixed if r.source_kind == "loan"]
        assert len(loan_rows) == 1
        assert loan_rows[0].amount == Decimal("1000.00")

    async def test_archived_reserve_excluded(self, session: AsyncSession):
        acc = await _make_account(session, "Savings", AccountType.SAVINGS)
        svc = ReserveFundService(session)
        fund = await svc.create(
            ReserveFundCreate(
                name="OldFund",
                kind=ReserveFundKind.VACATION,
                target_amount=Decimal("5000"),
                backing_mode=ReserveFundBackingMode.ACCOUNT,
                backing_account_id=acc,
            )
        )
        await svc.archive(fund.id)
        result = await WizardProjectionService(session).get_budget_builder_sources(2026)
        assert result.reserves == []

    async def test_cancelled_subscription_excluded(self, session: AsyncSession):
        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(
                name="CancelledSub",
                amount=Decimal("10"),
                cadence_days=30,
            )
        )
        await svc.cancel(sub.id)
        result = await WizardProjectionService(session).get_budget_builder_sources(2026)
        assert result.fixed == []

    async def test_fixed_ordering_subscriptions_before_loans_before_planned(
        self, session: AsyncSession
    ):
        acc = await _make_account(session, "Main")
        credit_acc = await _make_account(session, "Loan", AccountType.CREDIT)

        await PlannedTransactionService(session).create(
            PlannedTransactionCreate(
                name="Rent",
                account_id=acc,
                amount=Decimal("2000"),
                type=TransactionType.EXPENSE,
                frequency=RecurrenceFrequency.MONTHLY,
                interval=1,
                start_date=datetime.date(2026, 1, 1),
                is_active=True,
            )
        )
        await SubscriptionService(session).create(
            SubscriptionCreate(name="Spotify", amount=Decimal("20"), cadence_days=30)
        )
        await CreditService(session).create_loan(
            LoanProfileCreate(
                account_id=credit_acc,
                principal=Decimal("12000"),
                apr=Decimal("0"),
                term_months=12,
                start_date=datetime.date(2026, 1, 1),
            )
        )
        result = await WizardProjectionService(session).get_budget_builder_sources(2026)
        kinds = [r.source_kind for r in result.fixed]
        # Subscriptions first, then loans, then planned.
        assert kinds == ["subscription", "loan", "planned"]


# ── Payment Calendar projection ──────────────────────────────────────────────


class TestPaymentCalendarProjection:
    async def test_monthly_subscription_occurs_within_window(
        self, session: AsyncSession
    ):
        await SubscriptionService(session).create(
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("50"),
                cadence_days=30,
                first_seen_at=datetime.date(2026, 1, 5),
            )
        )
        start = datetime.date(2026, 4, 1)
        end = datetime.date(2026, 4, 30)
        result = await WizardProjectionService(session).get_payment_calendar_sources(
            start, end
        )
        # The monthly schedule from 2026-01-05 walks 05 Jan → 04 Feb → 06 Mar
        # → 05 Apr → 05 May (outside). Only 2026-04-05 falls inside.
        assert len(result.subscription_charges) == 1
        ch = result.subscription_charges[0]
        assert ch.date == datetime.date(2026, 4, 5)
        assert ch.name == "Netflix"

    async def test_empty_window_yields_empty(self, session: AsyncSession):
        result = await WizardProjectionService(session).get_payment_calendar_sources(
            datetime.date(2026, 4, 10), datetime.date(2026, 4, 1)
        )
        assert result.subscription_charges == []

    async def test_cancelled_subscription_not_projected(
        self, session: AsyncSession
    ):
        svc = SubscriptionService(session)
        sub = await svc.create(
            SubscriptionCreate(
                name="CancelledX",
                amount=Decimal("50"),
                cadence_days=30,
                first_seen_at=datetime.date(2026, 4, 1),
            )
        )
        await svc.cancel(sub.id)
        result = await WizardProjectionService(session).get_payment_calendar_sources(
            datetime.date(2026, 4, 1), datetime.date(2026, 4, 30)
        )
        assert result.subscription_charges == []
