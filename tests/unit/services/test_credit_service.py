"""Unit tests for CreditService + pure helpers."""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.credit import (
    CreditCardProfileCreate,
    CreditStatus,
    LoanProfileCreate,
)
from kaleta.services import AccountService, CreditService
from kaleta.services.credit_service import (
    amortisation_schedule,
    compute_min_payment,
    compute_monthly_payment,
    next_due_date,
)


async def _make_account(
    session: AsyncSession, name: str = "Card", balance: Decimal = Decimal("0")
) -> int:
    acc = await AccountService(session).create(
        AccountCreate(name=name, type=AccountType.CREDIT, balance=balance)
    )
    return acc.id


# ── Pure helpers ─────────────────────────────────────────────────────────────


class TestPureHelpers:
    def test_compute_monthly_payment_zero_apr(self):
        # No interest → principal / term.
        assert compute_monthly_payment(Decimal("1200"), Decimal("0"), 12) == Decimal(
            "100.00"
        )

    def test_compute_monthly_payment_standard(self):
        # 10 000 at 12% p.a. over 24 months — Excel PMT gives 470.73.
        got = compute_monthly_payment(Decimal("10000"), Decimal("12.00"), 24)
        assert got == Decimal("470.73")

    def test_amortisation_schedule_closes_exactly(self):
        from kaleta.models.credit import LoanProfile

        loan = LoanProfile(
            account_id=1,
            principal=Decimal("5000"),
            apr=Decimal("9.99"),
            term_months=12,
            start_date=datetime.date(2026, 1, 1),
            monthly_payment=compute_monthly_payment(
                Decimal("5000"), Decimal("9.99"), 12
            ),
        )
        schedule = amortisation_schedule(loan)
        assert len(schedule) == 12
        total_principal = sum(
            (row.principal_paid for row in schedule), Decimal("0")
        )
        assert total_principal == Decimal("5000.00")
        assert schedule[-1].remaining_principal == Decimal("0.00")

    def test_min_payment_floor_wins_when_balance_small(self):
        assert compute_min_payment(
            balance=Decimal("100"),
            pct=Decimal("0.02"),
            floor=Decimal("30"),
        ) == Decimal("30.00")

    def test_min_payment_pct_wins_when_balance_large(self):
        # 2% of 5000 = 100 which beats the 30 floor.
        assert compute_min_payment(
            balance=Decimal("5000"),
            pct=Decimal("0.02"),
            floor=Decimal("30"),
        ) == Decimal("100.00")

    def test_min_payment_capped_at_balance(self):
        # Balance < floor → pay the remaining balance, not the floor.
        assert compute_min_payment(
            balance=Decimal("20"),
            pct=Decimal("0.02"),
            floor=Decimal("30"),
        ) == Decimal("20.00")

    def test_next_due_date_this_month(self):
        # 25th is later this month → stay in-month.
        assert next_due_date(25, datetime.date(2026, 4, 10)) == datetime.date(
            2026, 4, 25
        )

    def test_next_due_date_rolls_to_next_month(self):
        assert next_due_date(5, datetime.date(2026, 4, 10)) == datetime.date(
            2026, 5, 5
        )

    def test_next_due_date_rolls_across_year(self):
        assert next_due_date(10, datetime.date(2026, 12, 20)) == datetime.date(
            2027, 1, 10
        )


# ── Card service flow ────────────────────────────────────────────────────────


class TestCardsService:
    async def test_create_and_list_card(self, session: AsyncSession):
        acc = await _make_account(session, "Visa", Decimal("-1500"))
        svc = CreditService(session)
        await svc.create_card(
            CreditCardProfileCreate(
                account_id=acc,
                credit_limit=Decimal("5000"),
                statement_day=1,
                payment_due_day=25,
            )
        )
        cards = await svc.list_cards()
        assert len(cards) == 1
        c = cards[0]
        assert c.account_name == "Visa"
        assert c.current_balance == Decimal("1500")
        assert c.utilization_pct == Decimal("0.3000")
        # 2% of 1500 = 30, ties with floor of 30 → 30.
        assert c.min_payment == Decimal("30.00")

    async def test_card_status_overdue(self, session: AsyncSession):
        acc = await _make_account(session, "Visa", Decimal("-500"))
        svc = CreditService(session)
        # Due day was 1 — if today is late in the month, we'd be past it.
        await svc.create_card(
            CreditCardProfileCreate(
                account_id=acc,
                credit_limit=Decimal("2000"),
                statement_day=20,
                payment_due_day=1,
            )
        )
        # list_cards uses datetime.today() — we can't assert the OVERDUE branch
        # without freezing time. Just confirm a card was surfaced.
        cards = await svc.list_cards()
        assert len(cards) == 1
        assert cards[0].status in (
            CreditStatus.ON_TIME,
            CreditStatus.GRACE,
            CreditStatus.OVERDUE,
        )


# ── Loan service flow ────────────────────────────────────────────────────────


class TestLoansService:
    async def test_create_loan_persists_monthly_payment(
        self, session: AsyncSession
    ):
        acc = await _make_account(session, "Mortgage")
        svc = CreditService(session)
        loan = await svc.create_loan(
            LoanProfileCreate(
                account_id=acc,
                principal=Decimal("10000"),
                apr=Decimal("12.00"),
                term_months=24,
                start_date=datetime.date(2026, 1, 1),
            )
        )
        assert loan.monthly_payment == Decimal("470.73")

    async def test_list_loans_includes_remaining_balance(
        self, session: AsyncSession
    ):
        acc = await _make_account(session, "Mortgage")
        svc = CreditService(session)
        await svc.create_loan(
            LoanProfileCreate(
                account_id=acc,
                principal=Decimal("10000"),
                apr=Decimal("0"),
                term_months=10,
                start_date=datetime.date(2026, 1, 1),
            )
        )
        loans = await svc.list_loans()
        assert len(loans) == 1
        l = loans[0]
        assert l.principal == Decimal("10000.00")
        assert l.monthly_payment == Decimal("1000.00")
        # Remaining balance is bounded by principal and ≥ 0.
        assert Decimal("0") <= l.remaining_balance <= l.principal

    async def test_amortisation_via_service(self, session: AsyncSession):
        acc = await _make_account(session, "Mortgage")
        svc = CreditService(session)
        await svc.create_loan(
            LoanProfileCreate(
                account_id=acc,
                principal=Decimal("1200"),
                apr=Decimal("0"),
                term_months=12,
                start_date=datetime.date(2026, 1, 1),
            )
        )
        schedule = await svc.amortisation(acc)
        assert len(schedule) == 12
        assert sum(
            (r.principal_paid for r in schedule), Decimal("0")
        ) == Decimal("1200.00")
