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
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, CategoryService, ReportService, TransactionService
from kaleta.services.import_service import ImportService
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
