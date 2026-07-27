# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for auto-categorisation rules.

Covers: KAL-RUL-003, KAL-RUL-004
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
from kaleta.schemas.categorisation_rule import CategorisationRuleCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.payee import PayeeCreate
from kaleta.schemas.transaction import TransactionCreate, TransactionUpdate
from kaleta.services import (
    AccountService,
    CategoryService,
    PayeeService,
    RuleService,
    TransactionService,
)
from kaleta.services.import_service import ImportService, ParsedRow
from kaleta.services.rule_service import SUGGESTION_THRESHOLD


@pytest.mark.asyncio
async def test_suggest_rule_from_repeated_manual_categorisation(
    session: AsyncSession,
) -> None:
    """Covers: KAL-RUL-003"""
    groceries = await CategoryService(session).create(
        CategoryCreate(name="Groceries", type=CategoryType.EXPENSE)
    )
    account = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING)
    )
    payee = await PayeeService(session).create(PayeeCreate(name="LIDL"))
    tx_svc = TransactionService(session)
    rule_svc = RuleService(session)

    for i in range(3):
        await tx_svc.create(
            TransactionCreate(
                account_id=account.id,
                category_id=groceries.id,
                payee_id=payee.id,
                amount=Decimal("10.00"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2024, 1, 1 + i),
                description="LIDL",
            )
        )

    await tx_svc.create(
        TransactionCreate(
            account_id=account.id,
            category_id=groceries.id,
            payee_id=payee.id,
            amount=Decimal("12.00"),
            type=TransactionType.EXPENSE,
            date=datetime.date(2024, 1, 4),
            description="LIDL",
        )
    )

    suggestion = await rule_svc.suggest_from_corrections(
        payee_name="LIDL",
        description="LIDL",
        category_id=groceries.id,
    )
    assert suggestion is not None
    assert suggestion.pattern == "LIDL"
    assert suggestion.category_name == "Groceries"
    assert suggestion.match_count >= SUGGESTION_THRESHOLD
    assert await rule_svc.list() == []


@pytest.mark.asyncio
async def test_manual_category_wins_over_rule(session: AsyncSession) -> None:
    """Covers: KAL-RUL-004"""
    groceries = await CategoryService(session).create(
        CategoryCreate(name="Groceries", type=CategoryType.EXPENSE)
    )
    alcohol = await CategoryService(session).create(
        CategoryCreate(name="Alcohol", type=CategoryType.EXPENSE)
    )
    default_expense = await CategoryService(session).create(
        CategoryCreate(name="Misc", type=CategoryType.EXPENSE)
    )
    account = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING)
    )
    await RuleService(session).create(
        CategorisationRuleCreate(pattern="LIDL", category_id=groceries.id)
    )

    import_svc = ImportService(session)
    creates = import_svc.to_transaction_creates(
        [
            ParsedRow(
                date=datetime.date(2024, 2, 1),
                amount=Decimal("-25.00"),
                description="LIDL shopping",
                raw={},
            )
        ],
        account_id=account.id,
        default_expense_category_id=default_expense.id,
    )
    creates = await import_svc.apply_categorisation_rules(creates)
    assert creates[0].category_id == groceries.id

    tx_svc = TransactionService(session)
    imported = await tx_svc.create(creates[0])
    assert imported.category_id == groceries.id

    updated = await tx_svc.update(imported.id, TransactionUpdate(category_id=alcohol.id))
    assert updated is not None
    assert updated.category_id == alcohol.id

    # Import-time re-match must not mutate the already-saved row
    rematched = await RuleService(session).match_category_id(
        payee_name=None,
        description="LIDL shopping",
    )
    assert rematched == groceries.id
    tx_id = imported.id
    session.expire_all()
    refetch = await tx_svc.get(tx_id)
    assert refetch is not None
    assert refetch.category_id == alcohol.id
