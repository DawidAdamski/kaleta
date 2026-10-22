# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transfer recognition over a real database: pair, suggest, keep out of totals.

Covers: KAL-TRF-001, KAL-TRF-002, KAL-TRF-003
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType, TransferDirection
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, CategoryService, ReportService, TransactionService
from kaleta.services.import_service import ImportService
from kaleta.views.components.amount_label import format_signed_amount, signed_amount_class
from kaleta.views.theme import AMOUNT_NEUTRAL, amount_class


async def _account(session: AsyncSession, name: str) -> int:
    account = await AccountService(session).create(
        AccountCreate(name=name, type=AccountType.CHECKING, currency="PLN")
    )
    return account.id


async def _category(session: AsyncSession, name: str, cat_type: CategoryType) -> int:
    category = await CategoryService(session).create(CategoryCreate(name=name, type=cat_type))
    return category.id


async def _row(
    session: AsyncSession,
    *,
    account_id: int,
    category_id: int,
    tx_type: TransactionType,
    amount: str,
    day: datetime.date,
    description: str,
) -> int:
    tx = await TransactionService(session).create(
        TransactionCreate(
            account_id=account_id,
            category_id=category_id,
            amount=Decimal(amount),
            type=tx_type,
            date=day,
            description=description,
        )
    )
    return tx.id


@pytest.mark.asyncio
async def test_manually_paired_rows_become_one_transfer(session: AsyncSession) -> None:
    """Covers: KAL-TRF-001"""
    mbank = await _account(session, "mBank")
    pko = await _account(session, "PKO BP")
    spend = await _category(session, "Other", CategoryType.EXPENSE)
    earn = await _category(session, "Other income", CategoryType.INCOME)
    expense_id = await _row(
        session,
        account_id=mbank,
        category_id=spend,
        tx_type=TransactionType.EXPENSE,
        amount="500.00",
        day=datetime.date(2026, 7, 1),
        description="Przelew własny",
    )
    income_id = await _row(
        session,
        account_id=pko,
        category_id=earn,
        tx_type=TransactionType.INCOME,
        amount="500.00",
        day=datetime.date(2026, 7, 1),
        description="Przelew własny",
    )

    out_leg, in_leg = await TransactionService(session).pair_as_transfer(expense_id, income_id)

    assert out_leg.account.name == "mBank"
    assert in_leg.account.name == "PKO BP"
    for leg in (out_leg, in_leg):
        assert leg.type == TransactionType.TRANSFER
        assert leg.is_internal_transfer is True
        assert leg.category_id is None
        assert leg.amount == Decimal("500.00")
    assert out_leg.linked_transaction_id == in_leg.id
    assert in_leg.linked_transaction_id == out_leg.id


@pytest.mark.asyncio
async def test_import_suggests_pairs_and_remembers_dismissals(session: AsyncSession) -> None:
    """Covers: KAL-TRF-002"""
    mbank = await _account(session, "mBank")
    pko = await _account(session, "PKO BP")
    spend = await _category(session, "Other", CategoryType.EXPENSE)
    earn = await _category(session, "Other income", CategoryType.INCOME)
    # Two matching pairs within 2 days, and one lone expense with no partner.
    savings_out = await _row(
        session,
        account_id=mbank,
        category_id=spend,
        tx_type=TransactionType.EXPENSE,
        amount="500.00",
        day=datetime.date(2026, 7, 1),
        description="Na oszczędności",
    )
    savings_in = await _row(
        session,
        account_id=pko,
        category_id=earn,
        tx_type=TransactionType.INCOME,
        amount="500.00",
        day=datetime.date(2026, 7, 3),
        description="Z mBanku",
    )
    rent_out = await _row(
        session,
        account_id=pko,
        category_id=spend,
        tx_type=TransactionType.EXPENSE,
        amount="1200.00",
        day=datetime.date(2026, 7, 5),
        description="Zwrot do mBanku",
    )
    rent_in = await _row(
        session,
        account_id=mbank,
        category_id=earn,
        tx_type=TransactionType.INCOME,
        amount="1200.00",
        day=datetime.date(2026, 7, 6),
        description="Z PKO",
    )
    await _row(
        session,
        account_id=mbank,
        category_id=spend,
        tx_type=TransactionType.EXPENSE,
        amount="87.40",
        day=datetime.date(2026, 7, 2),
        description="Biedronka",
    )
    imports = ImportService(session)

    suggestions = await imports.suggest_transfer_pairs()

    assert [(s.outgoing_id, s.incoming_id) for s in suggestions] == [
        (savings_out, savings_in),
        (rent_out, rent_in),
    ]
    # Suggesting links nothing.
    untouched = await TransactionService(session).get(savings_out)
    assert untouched is not None
    assert untouched.type == TransactionType.EXPENSE
    assert untouched.linked_transaction_id is None

    await imports.accept_transfer_pair(savings_out, savings_in)
    await imports.dismiss_transfer_pair(rent_out, rent_in)

    accepted = await TransactionService(session).get(savings_in)
    assert accepted is not None
    assert accepted.type == TransactionType.TRANSFER
    assert accepted.linked_transaction_id == savings_out
    dismissed = await TransactionService(session).get(rent_in)
    assert dismissed is not None
    assert dismissed.type == TransactionType.INCOME
    # Neither the accepted nor the dismissed pair comes back.
    assert await imports.suggest_transfer_pairs() == []


@pytest.mark.asyncio
async def test_recognised_transfer_is_out_of_month_totals_and_neutral(
    session: AsyncSession,
) -> None:
    """Covers: KAL-TRF-003"""
    today = datetime.date.today()
    mbank = await _account(session, "mBank")
    pko = await _account(session, "PKO BP")
    spend = await _category(session, "Groceries", CategoryType.EXPENSE)
    earn = await _category(session, "Salary", CategoryType.INCOME)
    await _row(
        session,
        account_id=pko,
        category_id=earn,
        tx_type=TransactionType.INCOME,
        amount="3000.00",
        day=today,
        description="Wypłata",
    )
    await _row(
        session,
        account_id=mbank,
        category_id=spend,
        tx_type=TransactionType.EXPENSE,
        amount="200.00",
        day=today,
        description="Biedronka",
    )
    expense_id = await _row(
        session,
        account_id=mbank,
        category_id=spend,
        tx_type=TransactionType.EXPENSE,
        amount="500.00",
        day=today,
        description="Przelew własny",
    )
    income_id = await _row(
        session,
        account_id=pko,
        category_id=earn,
        tx_type=TransactionType.INCOME,
        amount="500.00",
        day=today,
        description="Przelew własny",
    )
    reports = ReportService(session)
    assert await reports.current_month_summary() == (Decimal("3500.00"), Decimal("700.00"))

    out_leg, in_leg = await TransactionService(session).pair_as_transfer(expense_id, income_id)

    # The dashboard's month widgets read this pair of figures.
    assert await reports.current_month_summary() == (Decimal("3000.00"), Decimal("200.00"))
    # The ledger row for each leg is typed "transfer", which colours neutral.
    for leg in (out_leg, in_leg):
        row = TransactionService.build_table_row(leg, None, "none")
        assert row["type"] == "transfer"
        assert amount_class(row["type"]) == AMOUNT_NEUTRAL


@pytest.mark.asyncio
async def test_transfer_leg_is_signed_by_its_direction_in_the_ledger(
    session: AsyncSession,
) -> None:
    """A transfer's incoming leg reads positive on the account it arrived on.

    The outgoing leg left "mBank" (money out, negative); the incoming leg
    arrived on "PKO BP" (money in, positive) — not both negative as when the
    sign came from the type alone.

    Covers: KAL-TRF-005
    """
    today = datetime.date.today()
    mbank = await _account(session, "mBank")
    pko = await _account(session, "PKO BP")
    spend = await _category(session, "Groceries", CategoryType.EXPENSE)
    earn = await _category(session, "Salary", CategoryType.INCOME)
    expense_id = await _row(
        session,
        account_id=mbank,
        category_id=spend,
        tx_type=TransactionType.EXPENSE,
        amount="500.00",
        day=today,
        description="Przelew własny",
    )
    income_id = await _row(
        session,
        account_id=pko,
        category_id=earn,
        tx_type=TransactionType.INCOME,
        amount="500.00",
        day=today,
        description="Przelew własny",
    )

    out_leg, in_leg = await TransactionService(session).pair_as_transfer(expense_id, income_id)

    assert out_leg.account_id == mbank
    assert out_leg.transfer_direction is TransferDirection.OUT
    out_row = TransactionService.build_table_row(out_leg, None, "none")
    assert out_row["amount_value"] == "-500.00"
    assert out_row["amount"] == "-500.00"

    assert in_leg.account_id == pko
    assert in_leg.transfer_direction is TransferDirection.IN
    in_row = TransactionService.build_table_row(in_leg, None, "none")
    assert in_row["amount_value"] == "500.00"
    assert in_row["amount"] == "+500.00"


@pytest.mark.asyncio
async def test_recent_transactions_card_signs_transfer_legs_by_direction(
    session: AsyncSession,
) -> None:
    """The dashboard's recent-transactions card signs a transfer leg by direction.

    The card reads ``ReportService.recent_transactions`` — real ``Transaction``
    rows carrying ``transfer_direction`` — and formats each amount with the same
    view helpers the widget uses. The arriving leg must read positive, matching
    the ledger (KAL-TRF-005); from the type alone both legs would read negative.
    A transfer stays neutral in colour whichever way it went.

    Covers: KAL-DSH-011
    """
    today = datetime.date.today()
    mbank = await _account(session, "mBank DSH11")
    pko = await _account(session, "PKO BP DSH11")

    svc = TransactionService(session)
    # Non-internal transfer legs: a recognised internal pair is filtered out of
    # the recent-transactions card, so the legs that reach it are these.
    await svc.create(
        TransactionCreate(
            account_id=mbank,
            amount=Decimal("500.00"),
            type=TransactionType.TRANSFER,
            transfer_direction=TransferDirection.OUT,
            date=today,
            description="Przelew DSH11 out",
        )
    )
    await svc.create(
        TransactionCreate(
            account_id=pko,
            amount=Decimal("500.00"),
            type=TransactionType.TRANSFER,
            transfer_direction=TransferDirection.IN,
            date=today,
            description="Przelew DSH11 in",
        )
    )

    recent = await ReportService(session).recent_transactions(10)
    by_desc = {tx.description: tx for tx in recent}
    out_leg = by_desc["Przelew DSH11 out"]
    in_leg = by_desc["Przelew DSH11 in"]

    # The three widget sites: phone label + table amount, and the signed value
    # the amount cell reads to paint a zero neutral.
    assert (
        format_signed_amount(out_leg.amount, out_leg.type, out_leg.transfer_direction) == "-500.00"
    )
    assert format_signed_amount(in_leg.amount, in_leg.type, in_leg.transfer_direction) == "+500.00"
    assert (
        str(TransactionService.signed_amount(in_leg.amount, in_leg.type, in_leg.transfer_direction))
        == "500.00"
    )
    # Colour still follows the raw type: a transfer leg is neutral either way.
    assert (
        signed_amount_class(in_leg.amount, in_leg.type, in_leg.transfer_direction) == AMOUNT_NEUTRAL
    )
    assert (
        signed_amount_class(out_leg.amount, out_leg.type, out_leg.transfer_direction)
        == AMOUNT_NEUTRAL
    )
