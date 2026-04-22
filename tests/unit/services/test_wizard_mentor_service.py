"""Unit tests for WizardMentorService rule engine."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.institution import InstitutionType
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.institution import InstitutionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    InstitutionService,
)
from kaleta.services.wizard_mentor_service import (
    MentorSuggestion,
    WizardMentorService,
)


@pytest.fixture
def svc(session: AsyncSession) -> WizardMentorService:
    return WizardMentorService(session)


async def _account(session: AsyncSession) -> int:
    acc = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING)
    )
    return acc.id


async def _add_tx(
    session: AsyncSession,
    account_id: int,
    *,
    category_id: int | None,
    tx_type: TransactionType = TransactionType.EXPENSE,
) -> None:
    # Insert directly via ORM to allow NULL category_id on expenses — mirrors
    # what CSV imports produce before the user categorises rows.
    session.add(
        Transaction(
            account_id=account_id,
            category_id=category_id,
            amount=Decimal("10.00"),
            type=tx_type,
            date=datetime.date.today(),
            description="t",
        )
    )
    await session.commit()


async def test_empty_state_returns_no_suggestions(svc: WizardMentorService) -> None:
    assert await svc.suggestions() == []


async def test_uncategorised_rule_fires_over_threshold(
    svc: WizardMentorService, session: AsyncSession
) -> None:
    aid = await _account(session)
    for _ in range(WizardMentorService.UNCATEGORISED_THRESHOLD + 1):
        await _add_tx(session, aid, category_id=None)

    keys = {s.key for s in await svc.suggestions()}
    assert "uncategorised" in keys


async def test_uncategorised_rule_silent_at_or_below_threshold(
    svc: WizardMentorService, session: AsyncSession
) -> None:
    aid = await _account(session)
    for _ in range(WizardMentorService.UNCATEGORISED_THRESHOLD):
        await _add_tx(session, aid, category_id=None)

    keys = {s.key for s in await svc.suggestions()}
    assert "uncategorised" not in keys


async def test_uncategorised_rule_ignores_transfers(
    svc: WizardMentorService, session: AsyncSession
) -> None:
    aid = await _account(session)
    for _ in range(WizardMentorService.UNCATEGORISED_THRESHOLD + 5):
        await _add_tx(session, aid, category_id=None, tx_type=TransactionType.TRANSFER)

    keys = {s.key for s in await svc.suggestions()}
    assert "uncategorised" not in keys


async def test_no_budget_rule_fires_when_expense_cats_exist_no_budget(
    svc: WizardMentorService, session: AsyncSession
) -> None:
    await CategoryService(session).create(
        CategoryCreate(name="Food", type=CategoryType.EXPENSE)
    )

    keys = {s.key for s in await svc.suggestions()}
    assert "no_budget" in keys


async def test_no_budget_rule_silent_without_expense_categories(
    svc: WizardMentorService,
) -> None:
    keys = {s.key for s in await svc.suggestions()}
    assert "no_budget" not in keys


async def test_missing_logos_rule_fires_when_institution_has_no_logo(
    svc: WizardMentorService, session: AsyncSession
) -> None:
    await InstitutionService(session).create(
        InstitutionCreate(name="mBank", type=InstitutionType.BANK)
    )

    suggestions = {s.key: s for s in await svc.suggestions()}
    assert "missing_logos" in suggestions
    assert suggestions["missing_logos"].params.get("count") == 1


async def test_missing_logos_rule_silent_when_all_have_logo(
    svc: WizardMentorService, session: AsyncSession
) -> None:
    await InstitutionService(session).create(
        InstitutionCreate(
            name="mBank", type=InstitutionType.BANK, logo_path="/logos/foo.png"
        )
    )

    keys = {s.key for s in await svc.suggestions()}
    assert "missing_logos" not in keys


async def test_suggestions_are_mentor_suggestion_instances(
    svc: WizardMentorService, session: AsyncSession
) -> None:
    await CategoryService(session).create(
        CategoryCreate(name="Food", type=CategoryType.EXPENSE)
    )
    suggestions = await svc.suggestions()
    assert suggestions, "expected at least one suggestion"
    assert all(isinstance(s, MentorSuggestion) for s in suggestions)
    for s in suggestions:
        assert s.key and s.cta_url.startswith("/")
        assert s.title_key.startswith("wizard.mentor_")
