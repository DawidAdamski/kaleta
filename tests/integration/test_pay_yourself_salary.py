# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for Feature: Pay Yourself a Salary.

The scenarios are arithmetic over a fixed income window, so they are pinned
to a fixed "today" rather than driven through the browser — the wizard panel
renders exactly what ``SalaryService`` returns here.

Covers: KAL-SAL-001, KAL-SAL-002, KAL-SAL-003, KAL-SAL-004, KAL-SAL-005,
KAL-SAL-006
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import TransactionType, TransferDirection
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.salary import SalaryPlanCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    NetWorthService,
    PlannedTransactionService,
    SalaryService,
    TransactionService,
)

pytestmark = pytest.mark.asyncio

# 2026-06 is the running month, so the window's four complete months are
# 2026-02 … 2026-05 — the "last four complete months" of every scenario.
TODAY = datetime.date(2026, 6, 15)
FOUR_IRREGULAR_MONTHS = [
    (datetime.date(2026, 2, 10), Decimal("6000.00")),
    (datetime.date(2026, 3, 10), Decimal("9000.00")),
    (datetime.date(2026, 4, 10), Decimal("4000.00")),
    (datetime.date(2026, 5, 10), Decimal("12000.00")),
]
TWO_MONTHS_ONLY = FOUR_IRREGULAR_MONTHS[2:]


async def _seed_freelancer(
    session: AsyncSession, rows: list[tuple[datetime.date, Decimal]]
) -> tuple[int, int]:
    """Business + personal account, with ``rows`` invoiced into the business one."""
    accounts = AccountService(session)
    business = await accounts.create(AccountCreate(name="Business", type=AccountType.CHECKING))
    personal = await accounts.create(AccountCreate(name="Personal", type=AccountType.CHECKING))
    category = await CategoryService(session).create(
        CategoryCreate(name="Invoices", type=CategoryType.INCOME)
    )
    transactions = TransactionService(session)
    for when, amount in rows:
        await transactions.create(
            TransactionCreate(
                account_id=business.id,
                category_id=category.id,
                amount=amount,
                type=TransactionType.INCOME,
                date=when,
                description="invoice",
            )
        )
    return business.id, personal.id


async def test_proposal_is_the_worst_month_of_the_window(session: AsyncSession) -> None:
    """Covers: KAL-SAL-001"""
    await _seed_freelancer(session, FOUR_IRREGULAR_MONTHS)

    proposal = await SalaryService(session).propose(today=TODAY)

    assert proposal.salary == Decimal("4000.00")
    assert proposal.worst == Decimal("4000.00")
    assert proposal.best == Decimal("12000.00")


async def test_buffer_accumulates_the_surplus_above_the_salary(session: AsyncSession) -> None:
    """Covers: KAL-SAL-002"""
    await _seed_freelancer(session, FOUR_IRREGULAR_MONTHS)

    proposal = await SalaryService(session).propose(today=TODAY)

    assert proposal.final_buffer == Decimal("15000.00")


async def test_overriding_the_proposal_replays_the_buffer(session: AsyncSession) -> None:
    """Covers: KAL-SAL-003"""
    await _seed_freelancer(session, FOUR_IRREGULAR_MONTHS)
    svc = SalaryService(session)

    assert (await svc.propose(today=TODAY)).salary == Decimal("4000.00")
    overridden = await svc.propose(today=TODAY, override=Decimal("5000.00"))

    assert overridden.final_buffer == Decimal("11000.00")


async def test_accepting_the_proposal_creates_a_monthly_planned_transfer(
    session: AsyncSession,
) -> None:
    """Covers: KAL-SAL-004"""
    business_id, personal_id = await _seed_freelancer(session, FOUR_IRREGULAR_MONTHS)
    svc = SalaryService(session)
    proposal = await svc.propose(today=TODAY)
    assert proposal.salary == Decimal("4000.00")

    await svc.create_salary_plan(
        SalaryPlanCreate(
            name="Salary",
            amount=proposal.salary,
            from_account_id=business_id,
            to_account_id=personal_id,
            start_date=datetime.date(2026, 7, 1),
        )
    )

    # The Payment Calendar reads planned occurrences — the transfer must show up
    # there once a month, on the business account.
    occurrences = await PlannedTransactionService(session).get_occurrences(
        datetime.date(2026, 7, 1), datetime.date(2026, 9, 30)
    )
    salary_dates = [
        o.date for o in occurrences if o.name == "Salary" and o.amount == Decimal("4000.00")
    ]
    assert salary_dates == [
        datetime.date(2026, 7, 1),
        datetime.date(2026, 8, 1),
        datetime.date(2026, 9, 1),
    ]
    assert all(o.type == TransactionType.TRANSFER for o in occurrences if o.name == "Salary")

    planned = await PlannedTransactionService(session).list()
    assert [(p.account_id, p.frequency) for p in planned] == [
        (business_id, RecurrenceFrequency.MONTHLY)
    ]


async def test_too_little_history_makes_no_proposal(session: AsyncSession) -> None:
    """Covers: KAL-SAL-005"""
    await _seed_freelancer(session, TWO_MONTHS_ONLY)

    proposal = await SalaryService(session).propose(today=TODAY)

    assert len(proposal.months) == 2
    assert proposal.has_enough_history is False
    assert proposal.salary == Decimal("0.00")
    assert proposal.projection == []


async def test_posting_the_salary_transfer_moves_money_between_both_accounts(
    session: AsyncSession,
) -> None:
    """Posting a salary planned transfer debits the source and credits the target.

    Covers: KAL-SAL-006
    """
    business_id, personal_id = await _seed_freelancer(session, FOUR_IRREGULAR_MONTHS)
    plan = await SalaryService(session).create_salary_plan(
        SalaryPlanCreate(
            name="Salary",
            amount=Decimal("4000.00"),
            from_account_id=business_id,
            to_account_id=personal_id,
            start_date=datetime.date(2026, 7, 1),
        )
    )

    accounts = AccountService(session)
    net_worth = NetWorthService(session)
    business_before = await accounts.balance(business_id)
    personal_before = await accounts.balance(personal_id)
    net_worth_before = (await net_worth.get_summary()).net_worth

    posted = await PlannedTransactionService(session).post_occurrence(
        plan.id, datetime.date(2026, 7, 1)
    )

    # Both legs land: the outgoing one carries the occurrence, linked to the
    # incoming one on the target account.
    assert posted.account_id == business_id
    assert posted.transfer_direction == TransferDirection.OUT
    assert posted.linked_transaction_id is not None
    incoming = await TransactionService(session).get(posted.linked_transaction_id)
    assert incoming is not None
    assert incoming.account_id == personal_id
    assert incoming.transfer_direction == TransferDirection.IN

    business_after = await accounts.balance(business_id)
    personal_after = await accounts.balance(personal_id)
    # The business account balance falls by 4,000.00; the personal one rises by it.
    assert business_before - business_after == Decimal("4000.00")
    assert personal_after - personal_before == Decimal("4000.00")

    # Net worth is unchanged — the money stayed in the user's own accounts — and
    # the current month of the history reflects it consistently with the balance.
    summary_after = await net_worth.get_summary()
    assert summary_after.net_worth == net_worth_before
    assert summary_after.history[-1].net_worth == net_worth_before
