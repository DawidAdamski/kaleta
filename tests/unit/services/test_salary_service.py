# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for SalaryService (pay yourself a salary)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.salary import MonthlyIncome, SalaryBasis, SalaryPlanCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, CategoryService, SalaryService, TransactionService
from kaleta.services.salary_service import (
    MIN_HISTORY_MONTHS,
    _percentile,
    _project_buffer,
    _shift_month,
)

# The window is anchored on complete months, so "today" is fixed and the four
# seeded months are 2026-02 … 2026-05 (2026-06 is the running, partial month).
TODAY = datetime.date(2026, 6, 15)
IRREGULAR = [
    (datetime.date(2026, 2, 10), Decimal("6000.00")),
    (datetime.date(2026, 3, 10), Decimal("9000.00")),
    (datetime.date(2026, 4, 10), Decimal("4000.00")),
    (datetime.date(2026, 5, 10), Decimal("12000.00")),
]


async def _make_account(
    session: AsyncSession,
    name: str,
    currency: str = "PLN",
    type_: AccountType = AccountType.CHECKING,
) -> int:
    account = await AccountService(session).create(
        AccountCreate(name=name, type=type_, balance=Decimal("0"), currency=currency)
    )
    return account.id


async def _make_income_category(session: AsyncSession, name: str) -> int:
    category = await CategoryService(session).create(
        CategoryCreate(name=name, type=CategoryType.INCOME)
    )
    return category.id


async def _seed_income(
    session: AsyncSession,
    account_id: int,
    category_id: int,
    rows: list[tuple[datetime.date, Decimal]],
) -> None:
    svc = TransactionService(session)
    for when, amount in rows:
        await svc.create(
            TransactionCreate(
                account_id=account_id,
                category_id=category_id,
                amount=amount,
                type=TransactionType.INCOME,
                date=when,
                description="invoice",
            )
        )


# ── Pure helpers ─────────────────────────────────────────────────────────────


class TestPureHelpers:
    def test_shift_month_wraps_backwards_over_year_end(self):
        assert _shift_month(2026, 1, -1) == (2025, 12)
        assert _shift_month(2026, 5, -11) == (2025, 6)

    def test_shift_month_wraps_forwards_over_year_end(self):
        assert _shift_month(2025, 12, 1) == (2026, 1)

    def test_percentile_of_empty_series_is_zero(self):
        assert _percentile([], Decimal("0.5")) == Decimal("0.00")

    def test_percentile_of_single_sample_is_that_sample(self):
        assert _percentile([Decimal("4000")], Decimal("0.25")) == Decimal("4000.00")

    def test_percentile_interpolates_between_neighbours(self):
        series = [Decimal("6000"), Decimal("9000"), Decimal("4000"), Decimal("12000")]
        # Sorted: 4000 6000 9000 12000. Rank 0.25×3 = 0.75 → 4000 + 0.75×2000.
        assert _percentile(series, Decimal("0.25")) == Decimal("5500.00")
        # Rank 0.5×3 = 1.5 → 6000 + 0.5×3000.
        assert _percentile(series, Decimal("0.5")) == Decimal("7500.00")

    def test_project_buffer_accumulates_surplus(self):
        months = [
            MonthlyIncome(year=2026, month=2, total=Decimal("6000.00")),
            MonthlyIncome(year=2026, month=3, total=Decimal("9000.00")),
            MonthlyIncome(year=2026, month=4, total=Decimal("4000.00")),
            MonthlyIncome(year=2026, month=5, total=Decimal("12000.00")),
        ]
        points = _project_buffer(months, Decimal("4000.00"))
        assert [p.surplus for p in points] == [
            Decimal("2000.00"),
            Decimal("5000.00"),
            Decimal("0.00"),
            Decimal("8000.00"),
        ]
        assert [p.buffer for p in points] == [
            Decimal("2000.00"),
            Decimal("7000.00"),
            Decimal("7000.00"),
            Decimal("15000.00"),
        ]

    def test_project_buffer_allows_the_buffer_to_go_negative(self):
        months = [
            MonthlyIncome(year=2026, month=4, total=Decimal("1000.00")),
            MonthlyIncome(year=2026, month=5, total=Decimal("500.00")),
        ]
        points = _project_buffer(months, Decimal("2000.00"))
        assert [p.buffer for p in points] == [Decimal("-1000.00"), Decimal("-2500.00")]


# ── Income window ────────────────────────────────────────────────────────────


class TestIncomeByMonth:
    async def test_series_starts_at_the_first_earning_month(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(session, account_id, category_id, IRREGULAR)

        months, currencies = await SalaryService(session).income_by_month(today=TODAY)

        assert [(m.year, m.month) for m in months] == [
            (2026, 2),
            (2026, 3),
            (2026, 4),
            (2026, 5),
        ]
        assert [m.total for m in months] == [
            Decimal("6000.00"),
            Decimal("9000.00"),
            Decimal("4000.00"),
            Decimal("12000.00"),
        ]
        assert currencies == ["PLN"]

    async def test_running_month_is_excluded(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(
            session,
            account_id,
            category_id,
            [*IRREGULAR, (datetime.date(2026, 6, 3), Decimal("99000.00"))],
        )

        months, _ = await SalaryService(session).income_by_month(today=TODAY)

        assert (2026, 6) not in [(m.year, m.month) for m in months]
        assert max(m.total for m in months) == Decimal("12000.00")

    async def test_dry_month_inside_the_span_counts_as_zero(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(
            session,
            account_id,
            category_id,
            [
                (datetime.date(2026, 3, 10), Decimal("9000.00")),
                (datetime.date(2026, 5, 10), Decimal("12000.00")),
            ],
        )

        months, _ = await SalaryService(session).income_by_month(today=TODAY)

        assert [m.total for m in months] == [
            Decimal("9000.00"),
            Decimal("0.00"),
            Decimal("12000.00"),
        ]

    async def test_internal_transfers_are_excluded(self, session: AsyncSession):
        """An own-account top-up must not inflate the month it lands in.

        ``TransactionCreate`` refuses ``is_internal_transfer`` on a non-transfer
        row, but the column carries no such constraint — importers and the demo
        generator write ``Transaction`` rows directly, so the query filters on
        the flag rather than trusting the schema invariant.
        """
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(session, account_id, category_id, IRREGULAR)
        session.add(
            Transaction(
                account_id=account_id,
                category_id=category_id,
                amount=Decimal("50000.00"),
                type=TransactionType.INCOME,
                date=datetime.date(2026, 4, 20),
                description="own top-up",
                is_internal_transfer=True,
            )
        )
        await session.commit()

        months, _ = await SalaryService(session).income_by_month(today=TODAY)

        assert [m.total for m in months][2] == Decimal("4000.00")

    async def test_income_outside_the_window_is_ignored(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(
            session,
            account_id,
            category_id,
            [*IRREGULAR, (datetime.date(2024, 1, 10), Decimal("80000.00"))],
        )

        months, _ = await SalaryService(session).income_by_month(window_months=12, today=TODAY)

        assert (2024, 1) not in [(m.year, m.month) for m in months]

    async def test_no_income_at_all_yields_an_empty_series(self, session: AsyncSession):
        months, currencies = await SalaryService(session).income_by_month(today=TODAY)
        assert months == []
        assert currencies == []

    async def test_every_income_currency_is_reported(self, session: AsyncSession):
        pln_id = await _make_account(session, "Business PLN", currency="PLN")
        eur_id = await _make_account(session, "Business EUR", currency="EUR")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(session, pln_id, category_id, IRREGULAR)
        await _seed_income(
            session,
            eur_id,
            category_id,
            [(datetime.date(2026, 5, 12), Decimal("500.00"))],
        )

        _, currencies = await SalaryService(session).income_by_month(today=TODAY)

        assert currencies == ["EUR", "PLN"]

    async def test_zero_window_is_rejected(self, session: AsyncSession):
        with pytest.raises(ValidationError):
            await SalaryService(session).income_by_month(window_months=0, today=TODAY)


# ── Proposal ─────────────────────────────────────────────────────────────────


class TestPropose:
    async def test_worst_month_is_the_default_proposal(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(session, account_id, category_id, IRREGULAR)

        proposal = await SalaryService(session).propose(today=TODAY)

        assert proposal.basis == SalaryBasis.WORST
        assert proposal.salary == Decimal("4000.00")
        assert proposal.worst == Decimal("4000.00")
        assert proposal.best == Decimal("12000.00")
        assert proposal.has_enough_history is True

    async def test_alternative_bases_are_offered(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(session, account_id, category_id, IRREGULAR)

        svc = SalaryService(session)
        assert (await svc.propose(today=TODAY)).p25 == Decimal("5500.00")
        assert (await svc.propose(today=TODAY)).median == Decimal("7500.00")
        p25 = await svc.propose(today=TODAY, basis=SalaryBasis.P25)
        median = await svc.propose(today=TODAY, basis=SalaryBasis.MEDIAN)
        assert p25.salary == Decimal("5500.00")
        assert median.salary == Decimal("7500.00")

    async def test_buffer_projection_follows_the_proposal(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(session, account_id, category_id, IRREGULAR)

        proposal = await SalaryService(session).propose(today=TODAY)

        assert proposal.final_buffer == Decimal("15000.00")

    async def test_override_replaces_the_statistic(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(session, account_id, category_id, IRREGULAR)

        proposal = await SalaryService(session).propose(today=TODAY, override=Decimal("5000.00"))

        assert proposal.salary == Decimal("5000.00")
        assert proposal.final_buffer == Decimal("11000.00")

    async def test_negative_override_is_rejected(self, session: AsyncSession):
        with pytest.raises(ValidationError):
            await SalaryService(session).propose(today=TODAY, override=Decimal("-1"))

    async def test_short_history_makes_no_proposal(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(
            session,
            account_id,
            category_id,
            [
                (datetime.date(2026, 4, 10), Decimal("4000.00")),
                (datetime.date(2026, 5, 10), Decimal("12000.00")),
            ],
        )

        proposal = await SalaryService(session).propose(today=TODAY)

        assert len(proposal.months) < MIN_HISTORY_MONTHS
        assert proposal.has_enough_history is False
        assert proposal.salary == Decimal("0.00")
        assert proposal.projection == []

    async def test_multi_currency_income_is_flagged(self, session: AsyncSession):
        pln_id = await _make_account(session, "Business PLN", currency="PLN")
        eur_id = await _make_account(session, "Business EUR", currency="EUR")
        category_id = await _make_income_category(session, "Invoices")
        await _seed_income(session, pln_id, category_id, IRREGULAR)
        await _seed_income(
            session,
            eur_id,
            category_id,
            [(datetime.date(2026, 5, 12), Decimal("500.00"))],
        )

        proposal = await SalaryService(session).propose(today=TODAY)

        assert proposal.is_multi_currency is True


# ── Accepting a proposal ─────────────────────────────────────────────────────


class TestCreateSalaryPlan:
    async def test_creates_a_monthly_transfer_on_the_source_account(self, session: AsyncSession):
        business_id = await _make_account(session, "Business")
        personal_id = await _make_account(session, "Personal")

        planned = await SalaryService(session).create_salary_plan(
            SalaryPlanCreate(
                name="Salary",
                amount=Decimal("4000.00"),
                from_account_id=business_id,
                to_account_id=personal_id,
                start_date=datetime.date(2026, 7, 1),
            )
        )

        assert planned.type == TransactionType.TRANSFER
        assert planned.frequency == RecurrenceFrequency.MONTHLY
        assert planned.interval == 1
        assert planned.account_id == business_id
        assert planned.amount == Decimal("4000.00")
        assert planned.description == "Business → Personal"
        assert planned.is_active is True

    async def test_same_source_and_target_is_rejected(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")

        with pytest.raises(ValidationError):
            await SalaryService(session).create_salary_plan(
                SalaryPlanCreate(
                    name="Salary",
                    amount=Decimal("4000.00"),
                    from_account_id=account_id,
                    to_account_id=account_id,
                    start_date=datetime.date(2026, 7, 1),
                )
            )

    async def test_unknown_account_is_rejected(self, session: AsyncSession):
        account_id = await _make_account(session, "Business")

        with pytest.raises(NotFoundError):
            await SalaryService(session).create_salary_plan(
                SalaryPlanCreate(
                    name="Salary",
                    amount=Decimal("4000.00"),
                    from_account_id=account_id,
                    to_account_id=account_id + 999,
                    start_date=datetime.date(2026, 7, 1),
                )
            )
