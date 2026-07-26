# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for RuleService — auto-categorisation rules.

Covers: KAL-RUL-001, KAL-RUL-003, KAL-RUL-004
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
from kaleta.services.rule_service import SUGGESTION_THRESHOLD


@pytest.fixture
async def groceries(session: AsyncSession):
    return await CategoryService(session).create(
        CategoryCreate(name="Groceries", type=CategoryType.EXPENSE)
    )


@pytest.fixture
async def alcohol(session: AsyncSession):
    return await CategoryService(session).create(
        CategoryCreate(name="Alcohol", type=CategoryType.EXPENSE)
    )


@pytest.fixture
async def account(session: AsyncSession):
    return await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING, balance=Decimal("0.00"))
    )


class TestRuleServiceCreate:
    async def test_create_rule_appears_in_list(
        self, session: AsyncSession, groceries: object
    ) -> None:
        """Covers: KAL-RUL-001"""
        svc = RuleService(session)
        rule = await svc.create(
            CategorisationRuleCreate(
                pattern="LIDL",
                category_id=groceries.id,  # type: ignore[attr-defined]
            )
        )
        assert rule.id is not None
        assert rule.pattern == "LIDL"
        rules = await svc.list()
        assert len(rules) == 1
        assert rules[0].pattern == "LIDL"
        assert rules[0].category.name == "Groceries"


class TestRuleMatching:
    async def test_contains_case_insensitive_payee_then_description(
        self, session: AsyncSession, groceries: object
    ) -> None:
        """Covers: KAL-RUL-002 — match semantics used during import."""
        await RuleService(session).create(
            CategorisationRuleCreate(
                pattern="LIDL",
                category_id=groceries.id,  # type: ignore[attr-defined]
            )
        )
        svc = RuleService(session)
        assert (
            await svc.match_category_id(payee_name="Lidl Express", description="other")
            == groceries.id  # type: ignore[attr-defined]
        )
        assert (
            await svc.match_category_id(payee_name=None, description="Purchase at LIDL Warszawa")
            == groceries.id  # type: ignore[attr-defined]
        )
        assert await svc.match_category_id(payee_name="Orlen", description="Fuel") is None

    async def test_inactive_rules_skipped(self, session: AsyncSession, groceries: object) -> None:
        await RuleService(session).create(
            CategorisationRuleCreate(
                pattern="LIDL",
                category_id=groceries.id,  # type: ignore[attr-defined]
                is_active=False,
            )
        )
        assert (
            await RuleService(session).match_category_id(payee_name="LIDL", description="") is None
        )


class TestSuggestFromCorrections:
    async def test_offers_rule_after_fourth_same_categorisation(
        self,
        session: AsyncSession,
        groceries: object,
        account: object,
    ) -> None:
        """Covers: KAL-RUL-003"""
        payee = await PayeeService(session).create(PayeeCreate(name="LIDL"))
        tx_svc = TransactionService(session)
        rule_svc = RuleService(session)

        for i in range(3):
            await tx_svc.create(
                TransactionCreate(
                    account_id=account.id,  # type: ignore[attr-defined]
                    category_id=groceries.id,  # type: ignore[attr-defined]
                    payee_id=payee.id,
                    amount=Decimal("10.00"),
                    type=TransactionType.EXPENSE,
                    date=datetime.date(2024, 1, 1 + i),
                    description="LIDL",
                )
            )

        suggestion = await rule_svc.suggest_from_corrections(
            payee_name="LIDL",
            description="LIDL",
            category_id=groceries.id,  # type: ignore[attr-defined]
        )
        assert suggestion is None  # only three so far

        await tx_svc.create(
            TransactionCreate(
                account_id=account.id,  # type: ignore[attr-defined]
                category_id=groceries.id,  # type: ignore[attr-defined]
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
            category_id=groceries.id,  # type: ignore[attr-defined]
        )
        assert suggestion is not None
        assert suggestion.pattern == "LIDL"
        assert suggestion.category_name == "Groceries"
        assert suggestion.match_count >= SUGGESTION_THRESHOLD

        # Offer does not silently create
        assert await rule_svc.list() == []


class TestManualCategoryWins:
    async def test_manual_category_not_overwritten_by_rule(
        self,
        session: AsyncSession,
        groceries: object,
        alcohol: object,
        account: object,
    ) -> None:
        """Covers: KAL-RUL-004"""
        await RuleService(session).create(
            CategorisationRuleCreate(
                pattern="LIDL",
                category_id=groceries.id,  # type: ignore[attr-defined]
            )
        )
        tx_svc = TransactionService(session)
        tx = await tx_svc.create(
            TransactionCreate(
                account_id=account.id,  # type: ignore[attr-defined]
                category_id=groceries.id,  # type: ignore[attr-defined]
                amount=Decimal("25.00"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2024, 2, 1),
                description="LIDL shopping",
            )
        )
        updated = await tx_svc.update(
            tx.id,
            TransactionUpdate(category_id=alcohol.id),  # type: ignore[attr-defined]
        )
        assert updated is not None
        assert updated.category_id == alcohol.id  # type: ignore[attr-defined]

        # Re-matching must not mutate the saved transaction
        matched = await RuleService(session).match_category_id(
            payee_name=None,
            description=updated.description,
        )
        assert matched == groceries.id  # type: ignore[attr-defined]
        tx_id = tx.id
        session.expire_all()
        refetch = await tx_svc.get(tx_id)
        assert refetch is not None
        assert refetch.category_id == alcohol.id  # type: ignore[attr-defined]
        assert refetch.category is not None
        assert refetch.category.name == "Alcohol"
