# SPDX-License-Identifier: AGPL-3.0-or-later
"""Savings goals (skarbonki): target date, contributions, pace, close.

Covers: KAL-GOL-001, KAL-GOL-002, KAL-GOL-003, KAL-GOL-004
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.reserve_fund import (
    GoalClose,
    GoalContribution,
    ReserveFundCreate,
    ReserveFundKind,
    ReserveFundUpdate,
    ReserveFundWithProgress,
)
from kaleta.services import AccountService, ReserveFundService

TODAY = datetime.date(2026, 7, 1)


class _Goals:
    def __init__(self, session: AsyncSession) -> None:
        self.accounts = AccountService(session)
        self.funds = ReserveFundService(session)

    async def account(self, name: str, balance: str, currency: str = "PLN") -> int:
        created = await self.accounts.create(
            AccountCreate(
                name=name, type=AccountType.CHECKING, balance=Decimal(balance), currency=currency
            )
        )
        return created.id

    async def goal(self, backing_id: int, *, target_date: datetime.date | None = None) -> int:
        fund = await self.funds.create(
            ReserveFundCreate(
                name="Holidays 2027",
                kind=ReserveFundKind.VACATION,
                target_amount=Decimal("6000.00"),
                backing_account_id=backing_id,
                target_date=target_date,
            )
        )
        return fund.id

    async def contribute(self, fund_id: int, source_id: int, amount: str) -> None:
        await self.funds.contribute(
            fund_id,
            GoalContribution(
                amount=Decimal(amount), from_account_id=source_id, date=TODAY, description="wpłata"
            ),
        )

    async def progress(self, fund_id: int) -> ReserveFundWithProgress:
        fund = await self.funds.get(fund_id)
        assert fund is not None
        return await self.funds.with_progress(fund, today=TODAY)


@pytest.fixture
async def goals(session: AsyncSession) -> _Goals:
    return _Goals(session)


class TestScenarios:
    async def test_create_a_savings_goal(self, goals: _Goals) -> None:
        """Covers: KAL-GOL-001"""
        vault = await goals.account("Konto wakacyjne", "0.00")
        fund_id = await goals.goal(vault, target_date=datetime.date(2027, 6, 1))
        shown = await goals.progress(fund_id)
        assert shown.name == "Holidays 2027"
        assert shown.target_amount == Decimal("6000.00")
        assert shown.target_date == datetime.date(2027, 6, 1)
        assert shown.progress_pct == Decimal("0.00")

    async def test_contribute_to_a_goal(self, goals: _Goals) -> None:
        """Covers: KAL-GOL-002"""
        pko = await goals.account("PKO Main", "1000.00")
        vault = await goals.account("Konto wakacyjne", "0.00")
        fund_id = await goals.goal(vault)
        await goals.contribute(fund_id, pko, "500.00")
        shown = await goals.progress(fund_id)
        assert shown.current_balance == Decimal("500.00")
        assert round(shown.progress_pct * 100) == 8
        assert await goals.accounts.balance(pko) == Decimal("500.00")

    async def test_pace_hint_against_the_target_date(self, goals: _Goals) -> None:
        """Covers: KAL-GOL-003"""
        pko = await goals.account("PKO Main", "1000.00")
        vault = await goals.account("Konto wakacyjne", "0.00")
        fund_id = await goals.goal(vault, target_date=datetime.date(2027, 6, 1))
        await goals.contribute(fund_id, pko, "500.00")
        shown = await goals.progress(fund_id)
        assert shown.months_left == 11
        assert shown.monthly_pace == Decimal("500.00")

    async def test_close_a_goal_and_release_the_money(self, goals: _Goals) -> None:
        """Covers: KAL-GOL-004"""
        pko = await goals.account("PKO Main", "7000.00")
        vault = await goals.account("Konto wakacyjne", "0.00")
        fund_id = await goals.goal(vault)
        await goals.contribute(fund_id, pko, "6000.00")
        assert await goals.accounts.balance(pko) == Decimal("1000.00")

        source = await goals.funds.last_contribution_source(fund_id)
        assert source == pko
        await goals.funds.close(
            fund_id, GoalClose(release_to_account_id=source, date=TODAY, description="koniec")
        )

        assert await goals.accounts.balance(pko) == Decimal("7000.00")
        assert await goals.accounts.balance(vault) == Decimal("0.00")
        closed = await goals.funds.get(fund_id)
        assert closed is not None
        assert closed.is_archived is True


class TestPace:
    @pytest.mark.parametrize(
        ("today", "target", "months"),
        [
            (datetime.date(2026, 7, 1), datetime.date(2027, 6, 1), 11),
            (datetime.date(2026, 7, 15), datetime.date(2027, 6, 1), 10),
            (datetime.date(2026, 7, 1), datetime.date(2026, 7, 20), 0),
            (datetime.date(2026, 7, 1), datetime.date(2026, 5, 1), 0),
        ],
    )
    def test_months_left(self, today: datetime.date, target: datetime.date, months: int) -> None:
        assert ReserveFundService.months_left(today, target) == months

    def test_pace_rounds_up_to_the_grosz(self) -> None:
        assert ReserveFundService.monthly_pace(Decimal("100.00"), Decimal("0.00"), 3) == Decimal(
            "33.34"
        )

    def test_a_reached_goal_needs_nothing_more(self) -> None:
        assert ReserveFundService.monthly_pace(
            Decimal("6000.00"), Decimal("6100.00"), 4
        ) == Decimal("0.00")

    def test_with_no_whole_month_left_the_remainder_is_due_now(self) -> None:
        assert ReserveFundService.monthly_pace(
            Decimal("6000.00"), Decimal("5500.00"), 0
        ) == Decimal("500.00")

    async def test_a_goal_without_a_date_has_no_pace(self, goals: _Goals) -> None:
        vault = await goals.account("Konto wakacyjne", "0.00")
        shown = await goals.progress(await goals.goal(vault))
        assert shown.months_left is None
        assert shown.monthly_pace is None


class TestRules:
    def test_only_a_goal_has_a_target_date(self) -> None:
        with pytest.raises(PydanticValidationError, match="target_date"):
            ReserveFundCreate(
                name="Poduszka",
                kind=ReserveFundKind.EMERGENCY,
                target_amount=Decimal("3000.00"),
                backing_account_id=1,
                target_date=datetime.date(2027, 6, 1),
            )

    async def test_a_fund_edited_out_of_being_a_goal_drops_its_date(self, goals: _Goals) -> None:
        vault = await goals.account("Konto wakacyjne", "0.00")
        fund_id = await goals.goal(vault, target_date=datetime.date(2027, 6, 1))
        await goals.funds.update(fund_id, ReserveFundUpdate(kind=ReserveFundKind.IRREGULAR))
        fund = await goals.funds.get(fund_id)
        assert fund is not None
        assert fund.target_date is None

    async def test_only_a_goal_takes_contributions(self, goals: _Goals) -> None:
        pko = await goals.account("PKO Main", "1000.00")
        vault = await goals.account("Poduszka", "0.00")
        fund = await goals.funds.create(
            ReserveFundCreate(
                name="Poduszka",
                kind=ReserveFundKind.EMERGENCY,
                target_amount=Decimal("3000.00"),
                backing_account_id=vault,
            )
        )
        with pytest.raises(ValidationError):
            await goals.contribute(fund.id, pko, "100.00")

    async def test_a_contribution_from_the_goals_own_account_is_refused(
        self, goals: _Goals
    ) -> None:
        vault = await goals.account("Konto wakacyjne", "100.00")
        fund_id = await goals.goal(vault)
        with pytest.raises(ValidationError):
            await goals.contribute(fund_id, vault, "50.00")

    async def test_a_contribution_across_currencies_is_refused(self, goals: _Goals) -> None:
        wise = await goals.account("Wise EUR", "100.00", currency="EUR")
        vault = await goals.account("Konto wakacyjne", "0.00")
        fund_id = await goals.goal(vault)
        with pytest.raises(ValidationError):
            await goals.contribute(fund_id, wise, "50.00")
        assert await goals.accounts.balance(wise) == Decimal("100.00")

    async def test_a_closed_goal_takes_no_more_money(self, goals: _Goals) -> None:
        pko = await goals.account("PKO Main", "1000.00")
        vault = await goals.account("Konto wakacyjne", "0.00")
        fund_id = await goals.goal(vault)
        await goals.funds.close(
            fund_id, GoalClose(release_to_account_id=None, date=TODAY, description="")
        )
        with pytest.raises(ValidationError):
            await goals.contribute(fund_id, pko, "100.00")

    async def test_closing_without_an_account_leaves_the_money(self, goals: _Goals) -> None:
        pko = await goals.account("PKO Main", "1000.00")
        vault = await goals.account("Konto wakacyjne", "0.00")
        fund_id = await goals.goal(vault)
        await goals.contribute(fund_id, pko, "300.00")
        await goals.funds.close(
            fund_id, GoalClose(release_to_account_id=None, date=TODAY, description="")
        )
        assert await goals.accounts.balance(vault) == Decimal("300.00")

    async def test_a_goal_nobody_paid_into_has_no_source(self, goals: _Goals) -> None:
        vault = await goals.account("Konto wakacyjne", "0.00")
        assert await goals.funds.last_contribution_source(await goals.goal(vault)) is None
