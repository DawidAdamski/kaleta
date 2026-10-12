# SPDX-License-Identifier: AGPL-3.0-or-later
"""The annual review: the year in numbers, the carry into the next, the commitments.

``budgets-annual-review``. Expected figures are the scenarios' literals.

Covers: KAL-ANR-001, KAL-ANR-002, KAL-ANR-003
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.subscription import SubscriptionStatus
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.annual_review import CommitmentKind
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.category import CategoryCreate, CategoryType
from kaleta.schemas.irregular_item import IrregularItemCreate
from kaleta.schemas.reserve_fund import ReserveFundCreate, ReserveFundKind
from kaleta.schemas.subscription import SubscriptionCreate
from kaleta.schemas.transaction import TransactionCreate, TransactionType
from kaleta.schemas.yearly_plan import FixedLine, YearlyPlanPayload
from kaleta.services import (
    AccountService,
    AnnualReviewService,
    BudgetService,
    CategoryService,
    IrregularItemService,
    ReserveFundService,
    SubscriptionService,
    TransactionService,
    YearlyPlanService,
)

YEAR = 2025


class _Year:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.review = AnnualReviewService(session)
        self.budgets = BudgetService(session)

    async def category(self, name: str) -> int:
        created = await CategoryService(self.session).create(
            CategoryCreate(name=name, type=CategoryType.EXPENSE)
        )
        return created.id

    async def monthly_budget(self, category_id: int, amount: str, year: int = YEAR) -> None:
        await self.budgets.bulk_upsert(
            [
                BudgetCreate(category_id=category_id, amount=Decimal(amount), month=m, year=year)
                for m in range(1, 13)
            ]
        )

    async def spend(self, category_id: int, amount: str, month: int) -> None:
        account = await AccountService(self.session).create(
            AccountCreate(name=f"Konto {month}", type=AccountType.CHECKING)
        )
        await TransactionService(self.session).create(
            TransactionCreate(
                account_id=account.id,
                category_id=category_id,
                amount=Decimal(amount),
                type=TransactionType.EXPENSE,
                date=datetime.date(YEAR, month, 10),
            )
        )

    async def next_year_totals(self) -> dict[int, Decimal]:
        totals: dict[int, Decimal] = {}
        for budget in await self.budgets.list_for_year(YEAR + 1):
            totals[budget.category_id] = (
                totals.get(budget.category_id, Decimal("0")) + budget.amount
            )
        return totals


@pytest.fixture
async def year(session: AsyncSession) -> _Year:
    return _Year(session)


async def test_the_review_sums_up_the_closing_year(year: _Year) -> None:
    """Covers: KAL-ANR-001"""
    food = await year.category("Food")
    insurance = await year.category("Insurance")
    await year.monthly_budget(food, "500.00")
    await year.monthly_budget(insurance, "100.00")
    await year.spend(food, "5800.00", 6)
    await year.spend(insurance, "1250.00", 3)

    summary = await year.review.summary(YEAR)
    by_name = {r.name: r for r in summary.rows}
    assert (by_name["Food"].planned, by_name["Food"].actual) == (
        Decimal("6000.00"),
        Decimal("5800.00"),
    )
    assert (by_name["Insurance"].planned, by_name["Insurance"].actual) == (
        Decimal("1200.00"),
        Decimal("1250.00"),
    )
    assert by_name["Insurance"].difference == Decimal("-50.00")
    assert (summary.planned_total, summary.actual_total) == (
        Decimal("7200.00"),
        Decimal("7050.00"),
    )


async def test_the_budgets_carry_into_next_year_with_a_raise(year: _Year) -> None:
    """Covers: KAL-ANR-002"""
    food = await year.category("Food")
    insurance = await year.category("Insurance")
    await year.monthly_budget(food, "500.00")
    await year.monthly_budget(insurance, "100.00")

    carry = await year.review.carry(YEAR, {insurance: Decimal("10")})
    assert {r.name: r.next_amount for r in carry.rows} == {
        "Food": Decimal("6000.00"),
        "Insurance": Decimal("1320.00"),
    }
    assert not carry.replaces_plan
    await YearlyPlanService(year.session).apply(carry.payload)

    totals = await year.next_year_totals()
    assert totals == {food: Decimal("6000.00"), insurance: Decimal("1320.00")}
    assert (await YearlyPlanService(year.session).get(YEAR + 1)) is not None


async def test_the_carry_keeps_this_years_lines_and_moves_them(year: _Year) -> None:
    insurance = await year.category("Insurance")
    plans = YearlyPlanService(year.session)
    await plans.apply(
        YearlyPlanPayload(
            year=YEAR,
            fixed_lines=[
                FixedLine(name="OC/AC", amount=Decimal("1200.00"), category_id=insurance),
                FixedLine(name="Czynsz", amount=Decimal("24000.00")),
            ],
        )
    )

    carry = await year.review.carry(YEAR, {insurance: Decimal("10")})
    assert [(f.name, f.amount) for f in carry.payload.fixed_lines] == [
        ("OC/AC", Decimal("1320.00")),
        # No category: nothing to move it by.
        ("Czynsz", Decimal("24000.00")),
    ]
    # The lines already derive this year's budgets: no extra line for them.
    assert carry.payload.variable_lines == []

    await plans.apply(carry.payload)
    assert (await year.review.carry(YEAR)).replaces_plan


async def test_each_commitment_is_kept_adjusted_or_dropped(year: _Year) -> None:
    """Covers: KAL-ANR-003"""
    subs = SubscriptionService(year.session)
    netflix = await subs.create(
        SubscriptionCreate(name="Netflix", amount=Decimal("49.00"), cadence_days=30)
    )
    spotify = await subs.create(
        SubscriptionCreate(name="Spotify", amount=Decimal("23.99"), cadence_days=30)
    )
    account = await AccountService(year.session).create(
        AccountCreate(name="Konto funduszu", type=AccountType.SAVINGS)
    )
    fund = await ReserveFundService(year.session).create(
        ReserveFundCreate(
            name="Wydatki nieregularne",
            kind=ReserveFundKind.IRREGULAR,
            target_amount=Decimal("0"),
            backing_account_id=account.id,
        )
    )
    items = IrregularItemService(year.session)
    insurance = await items.create(
        fund.id, IrregularItemCreate(name="Car insurance", yearly_amount=Decimal("1200.00"))
    )

    rows = await year.review.commitments()
    assert [(r.kind, r.name, r.yearly) for r in rows] == [
        (CommitmentKind.SUBSCRIPTION, "Netflix", Decimal("596.17")),
        (CommitmentKind.SUBSCRIPTION, "Spotify", Decimal("291.88")),
        (CommitmentKind.IRREGULAR_ITEM, "Car insurance", Decimal("1200.00")),
    ]

    await year.review.adjust(CommitmentKind.IRREGULAR_ITEM, insurance.id, Decimal("1350.00"))
    await year.review.drop(CommitmentKind.SUBSCRIPTION, spotify.id)

    assert (await items.plan(fund.id)).items[0].yearly_amount == Decimal("1350.00")
    dropped = await subs.get(spotify.id)
    assert dropped is not None and dropped.status is SubscriptionStatus.CANCELLED
    assert [r.name for r in await year.review.commitments()] == ["Netflix", "Car insurance"]
    kept = await subs.get(netflix.id)
    assert kept is not None and kept.amount == Decimal("49.00")
