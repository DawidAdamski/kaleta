# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for WizardActionService — uses in-memory SQLite.

One class per contributing wizard section, plus ranking and the empty case.
"""

from __future__ import annotations

import datetime
import time
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.personal_loan import LoanDirection
from kaleta.models.reserve_fund import ReserveFundBackingMode, ReserveFundKind
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.personal_loan import (
    CounterpartyCreate,
    PersonalLoanCreate,
    RepaymentCreate,
)
from kaleta.schemas.reserve_fund import ReserveFundCreate
from kaleta.schemas.subscription import SubscriptionCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.schemas.wizard_actions import ActionKind, ActionSection, ActionSeverity
from kaleta.services import (
    AccountService,
    CategoryService,
    PersonalLoanService,
    ReserveFundService,
    SubscriptionService,
    TransactionService,
    WizardActionService,
)

# A mid-month reference date: far enough from month-end that the
# "plan next month" rule stays quiet unless a test wants it.
TODAY = datetime.date(2026, 6, 10)


@pytest.fixture
def svc(session: AsyncSession) -> WizardActionService:
    return WizardActionService(session)


async def _make_account(session: AsyncSession, balance: Decimal = Decimal("0")) -> int:
    acc = await AccountService(session).create(
        AccountCreate(name="Main", type=AccountType.CHECKING, balance=balance)
    )
    return acc.id


async def _make_loan_due(session: AsyncSession, *, due_at: datetime.date, name: str) -> int:
    loans = PersonalLoanService(session)
    cp = await loans.create_counterparty(CounterpartyCreate(name=name))
    loan = await loans.create_loan(
        PersonalLoanCreate(
            counterparty_id=cp.id,
            direction=LoanDirection.OUTGOING,
            principal=Decimal("500.00"),
            opened_at=datetime.date(2026, 1, 1),
            due_at=due_at,
        )
    )
    return loan.id


async def _make_fund(session: AsyncSession, *, target: Decimal, balance: Decimal) -> int:
    account_id = await _make_account(session, balance=balance)
    fund = await ReserveFundService(session).create(
        ReserveFundCreate(
            name="Emergency",
            kind=ReserveFundKind.VACATION,
            target_amount=target,
            backing_mode=ReserveFundBackingMode.ACCOUNT,
            backing_account_id=account_id,
        )
    )
    return fund.id


class TestEmptyState:
    async def test_no_data_yields_no_items(self, svc: WizardActionService):
        """Covers: KAL-WAC-001"""
        assert await svc.get_action_items(today=TODAY) == []


class TestPersonalLoans:
    async def test_loan_due_in_three_days_is_a_warning(
        self, svc: WizardActionService, session: AsyncSession
    ):
        """Covers: KAL-WAC-003"""
        await _make_loan_due(session, due_at=TODAY + datetime.timedelta(days=3), name="Ala")

        items = await svc.get_action_items(today=TODAY)

        assert len(items) == 1
        assert items[0].kind is ActionKind.LOAN_DUE_SOON
        assert items[0].severity is ActionSeverity.WARNING
        assert items[0].section is ActionSection.PERSONAL_LOANS
        assert items[0].params["days"] == 3

    async def test_overdue_loan_is_a_danger(self, svc: WizardActionService, session: AsyncSession):
        """Covers: KAL-WAC-003"""
        await _make_loan_due(session, due_at=TODAY - datetime.timedelta(days=3), name="Ala")

        items = await svc.get_action_items(today=TODAY)

        assert len(items) == 1
        assert items[0].kind is ActionKind.LOAN_OVERDUE
        assert items[0].severity is ActionSeverity.DANGER
        assert items[0].params["days"] == 3

    async def test_loan_beyond_the_horizon_stays_quiet(
        self, svc: WizardActionService, session: AsyncSession
    ):
        await _make_loan_due(session, due_at=TODAY + datetime.timedelta(days=30), name="Ala")
        assert await svc.get_action_items(today=TODAY) == []

    async def test_loan_without_a_due_date_stays_quiet(
        self, svc: WizardActionService, session: AsyncSession
    ):
        await _make_loan_due(session, due_at=None, name="Ala")  # type: ignore[arg-type]
        assert await svc.get_action_items(today=TODAY) == []

    async def test_settled_loan_stays_quiet(self, svc: WizardActionService, session: AsyncSession):
        loans = PersonalLoanService(session)
        loan_id = await _make_loan_due(
            session, due_at=TODAY - datetime.timedelta(days=3), name="Ala"
        )
        account_id = await _make_account(session)
        await loans.record_repayment(
            loan_id,
            RepaymentCreate(amount=Decimal("500.00"), date=TODAY, account_id=account_id),
        )

        assert await svc.get_action_items(today=TODAY) == []


class TestSubscriptions:
    async def test_past_due_renewal_is_listed_with_a_focus_link(
        self, svc: WizardActionService, session: AsyncSession
    ):
        """Covers: KAL-WAC-002"""
        sub = await SubscriptionService(session).create(
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("43.00"),
                next_expected_at=TODAY - datetime.timedelta(days=2),
            )
        )

        items = await svc.get_action_items(today=TODAY)

        assert len(items) == 1
        assert items[0].kind is ActionKind.SUBSCRIPTION_RENEWAL_DUE
        assert items[0].severity is ActionSeverity.INFO
        assert items[0].href == f"/wizard/subscriptions?focus={sub.id}"
        assert items[0].params["name"] == "Netflix"

    async def test_muted_subscription_stays_quiet(
        self, svc: WizardActionService, session: AsyncSession
    ):
        sub_svc = SubscriptionService(session)
        sub = await sub_svc.create(
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("43.00"),
                next_expected_at=TODAY - datetime.timedelta(days=2),
            )
        )
        await sub_svc.mute_one_cycle(sub.id, today=TODAY)

        assert await svc.get_action_items(today=TODAY) == []

    async def test_cancelled_subscription_stays_quiet(
        self, svc: WizardActionService, session: AsyncSession
    ):
        sub_svc = SubscriptionService(session)
        sub = await sub_svc.create(
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("43.00"),
                next_expected_at=TODAY - datetime.timedelta(days=2),
            )
        )
        await sub_svc.cancel(sub.id, today=TODAY)

        assert await svc.get_action_items(today=TODAY) == []

    async def test_future_renewal_stays_quiet(
        self, svc: WizardActionService, session: AsyncSession
    ):
        await SubscriptionService(session).create(
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("43.00"),
                next_expected_at=TODAY + datetime.timedelta(days=5),
            )
        )
        assert await svc.get_action_items(today=TODAY) == []


class TestSafetyFunds:
    async def test_fund_below_target_is_a_warning(
        self, svc: WizardActionService, session: AsyncSession
    ):
        fund_id = await _make_fund(session, target=Decimal("1000"), balance=Decimal("250"))

        items = await svc.get_action_items(today=TODAY)

        assert len(items) == 1
        assert items[0].kind is ActionKind.FUND_BELOW_TARGET
        assert items[0].severity is ActionSeverity.WARNING
        assert items[0].section is ActionSection.SAFETY_FUNDS
        assert items[0].href == f"/wizard/safety-funds?focus={fund_id}"
        assert items[0].params["pct"] == 25

    async def test_fully_funded_fund_stays_quiet(
        self, svc: WizardActionService, session: AsyncSession
    ):
        await _make_fund(session, target=Decimal("1000"), balance=Decimal("1000"))
        assert await svc.get_action_items(today=TODAY) == []


class TestMonthlyReadiness:
    async def test_fires_close_to_month_end(self, svc: WizardActionService):
        # 2026-06-28: two days left in a 30-day month.
        items = await svc.get_action_items(today=datetime.date(2026, 6, 28))

        assert len(items) == 1
        assert items[0].kind is ActionKind.PLAN_NEXT_MONTH
        assert items[0].section is ActionSection.MONTHLY_READINESS
        assert items[0].params["days"] == 2

    async def test_quiet_mid_month(self, svc: WizardActionService):
        assert await svc.get_action_items(today=TODAY) == []


class TestGettingStarted:
    async def test_mentor_hint_becomes_a_dismissable_item(
        self, svc: WizardActionService, session: AsyncSession
    ):
        account_id = await _make_account(session)
        cat_id = (
            await CategoryService(session).create(
                CategoryCreate(name="Food", type=CategoryType.EXPENSE)
            )
        ).id
        # Six un-categorised transactions trips the mentor's threshold of 5.
        for i in range(6):
            await TransactionService(session).create(
                TransactionCreate(
                    account_id=account_id,
                    category_id=None,
                    amount=Decimal("10.00"),
                    type=TransactionType.TRANSFER,
                    date=TODAY - datetime.timedelta(days=i),
                )
            )
            await TransactionService(session).create(
                TransactionCreate(
                    account_id=account_id,
                    category_id=cat_id,
                    amount=Decimal("10.00"),
                    type=TransactionType.EXPENSE,
                    date=TODAY - datetime.timedelta(days=i),
                )
            )

        items = await svc.get_action_items(today=TODAY)
        hints = [i for i in items if i.kind is ActionKind.MENTOR_HINT]

        assert hints, "expected at least one mentor hint"
        assert all(h.section is ActionSection.GETTING_STARTED for h in hints)
        assert all(h.dismiss_key for h in hints)


class TestRanking:
    async def test_danger_then_warning_then_info(
        self, svc: WizardActionService, session: AsyncSession
    ):
        """Covers: KAL-WAC-004"""
        await _make_loan_due(session, due_at=TODAY - datetime.timedelta(days=1), name="Overdue")
        await _make_fund(session, target=Decimal("1000"), balance=Decimal("250"))
        await SubscriptionService(session).create(
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("43.00"),
                next_expected_at=TODAY - datetime.timedelta(days=2),
            )
        )

        items = await svc.get_action_items(today=TODAY)

        assert [i.severity for i in items] == [
            ActionSeverity.DANGER,
            ActionSeverity.WARNING,
            ActionSeverity.INFO,
        ]

    async def test_newer_first_inside_a_severity_bucket(
        self, svc: WizardActionService, session: AsyncSession
    ):
        """Covers: KAL-WAC-004"""
        await _make_loan_due(session, due_at=TODAY - datetime.timedelta(days=10), name="Older")
        await _make_loan_due(session, due_at=TODAY - datetime.timedelta(days=1), name="Newer")

        items = await svc.get_action_items(today=TODAY)

        assert [i.params["name"] for i in items] == ["Newer", "Older"]


class TestPerformance:
    async def test_aggregates_under_200ms_on_a_thousand_transactions(
        self, svc: WizardActionService, session: AsyncSession
    ):
        """Plan acceptance criterion: < 200 ms on a seeded DB of ~1000 transactions."""
        account_id = await _make_account(session)
        cat_id = (
            await CategoryService(session).create(
                CategoryCreate(name="Food", type=CategoryType.EXPENSE)
            )
        ).id
        await TransactionService(session).create_bulk(
            [
                TransactionCreate(
                    account_id=account_id,
                    category_id=cat_id,
                    amount=Decimal("10.00"),
                    type=TransactionType.EXPENSE,
                    date=TODAY - datetime.timedelta(days=i % 365),
                    description=f"Merchant {i % 40}",
                )
                for i in range(1000)
            ]
        )

        start = time.perf_counter()
        await svc.get_action_items(today=TODAY)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 200, f"aggregation took {elapsed_ms:.0f} ms"
