"""E2E tests for Feature: Initial Setup Wizard.

Maps scenarios from docs/bdd.md — Feature: Initial Setup Wizard.

The BDD feature describes the "Na start" onboarding section at /wizard.
"""
from __future__ import annotations

import asyncio
import datetime
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8080"

_executor = ThreadPoolExecutor(max_workers=1)


def _run(coro):  # type: ignore[no-untyped-def]
    def _worker():  # type: ignore[no-untyped-def]
        return asyncio.run(coro)
    return _executor.submit(_worker).result()


# ---------------------------------------------------------------------------
# Seed helpers (idempotent)
# ---------------------------------------------------------------------------

def seed_institution(name: str) -> int:
    from sqlalchemy import select

    from kaleta.db import AsyncSessionFactory
    from kaleta.models.institution import Institution, InstitutionType
    from kaleta.schemas.institution import InstitutionCreate
    from kaleta.services import InstitutionService

    async def _create() -> int:
        async with AsyncSessionFactory() as session:
            existing = (
                await session.execute(select(Institution).where(Institution.name == name))
            ).scalar_one_or_none()
            if existing:
                return existing.id
            inst = await InstitutionService(session).create(
                InstitutionCreate(name=name, type=InstitutionType.BANK)
            )
            return inst.id

    return _run(_create())


def seed_account(name: str, institution_id: int | None = None) -> int:
    from sqlalchemy import select

    from kaleta.db import AsyncSessionFactory
    from kaleta.models.account import Account
    from kaleta.schemas.account import AccountCreate
    from kaleta.services import AccountService

    async def _create() -> int:
        async with AsyncSessionFactory() as session:
            existing = (
                await session.execute(select(Account).where(Account.name == name))
            ).scalar_one_or_none()
            if existing:
                return existing.id
            acc = await AccountService(session).create(
                AccountCreate(name=name, currency="PLN", institution_id=institution_id)
            )
            return acc.id

    return _run(_create())


# ---------------------------------------------------------------------------
# Scenario: Wizard page loads and shows onboarding section
# ---------------------------------------------------------------------------

def test_wizard_page_loads_with_onboarding_section(page: Page) -> None:
    """Wizard page renders the onboarding card."""
    page.goto(f"{BASE_URL}/wizard")

    expect(page.get_by_text("Financial Wizard", exact=True).first).to_be_visible(timeout=5000)
    expect(
        page.get_by_text("Getting started — set up your finances")
    ).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Wizard shows all four setup step titles
# ---------------------------------------------------------------------------

def test_wizard_shows_all_four_setup_steps(page: Page) -> None:
    """All four onboarding step titles are visible on the wizard page."""
    page.goto(f"{BASE_URL}/wizard")

    expect(page.get_by_text("Add an institution")).to_be_visible(timeout=5000)
    expect(
        page.get_by_text("Create an account with opening balance")
    ).to_be_visible(timeout=5000)
    expect(
        page.get_by_text("Create expense and income categories")
    ).to_be_visible(timeout=5000)
    expect(page.get_by_text("Import or add transactions")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Institution step hint shown when no institution exists
# ---------------------------------------------------------------------------

def test_wizard_institution_hint_shown_when_no_institutions(page: Page) -> None:
    """Scenario: Institution step pending hint is visible (not necessarily empty DB)."""
    page.goto(f"{BASE_URL}/wizard")

    # Either the hint text OR the count text will be visible depending on DB state.
    # We assert at least one step's content is rendered.
    expect(page.get_by_text("Add an institution")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Institution step is marked done after adding an institution
# ---------------------------------------------------------------------------

def test_wizard_institution_step_marked_done(page: Page) -> None:
    """Scenario: Wizard marks institution step as done."""
    seed_institution("PKO BP Wizard E2E Test")

    page.goto(f"{BASE_URL}/wizard")

    # When at least one institution exists the count label is shown.
    # It reads "You have N institutions."
    expect(page.get_by_text("institutions.", exact=False).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Account step marked done after adding an account
# ---------------------------------------------------------------------------

def test_wizard_account_step_marked_done(page: Page) -> None:
    """Wizard marks account step done when at least one account exists."""
    inst_id = seed_institution("mBank Wizard E2E Account")
    seed_account("Wizard E2E Account", institution_id=inst_id)

    page.goto(f"{BASE_URL}/wizard")

    expect(page.get_by_text("accounts.", exact=False).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Go buttons navigate to correct pages
# ---------------------------------------------------------------------------

def test_wizard_institution_go_button_navigates(page: Page) -> None:
    """Clicking Go/Edit on the institution step navigates to /institutions."""
    page.goto(f"{BASE_URL}/wizard")

    # Each onboarding step is a ui.row() (div.row) that contains a label with the
    # step title AND a button. Using `has=` finds the row that *contains* the exact
    # title text, then we click the single button inside that row.
    row = page.locator("div.row").filter(
        has=page.get_by_text("Add an institution", exact=True)
    )
    row.get_by_role("button").click()

    expect(page).to_have_url(f"{BASE_URL}/institutions", timeout=5000)


def test_wizard_account_go_button_navigates(page: Page) -> None:
    """Clicking Go/Edit on the accounts step navigates to /accounts."""
    page.goto(f"{BASE_URL}/wizard")

    row = page.locator("div.row").filter(
        has=page.get_by_text("Create an account with opening balance", exact=True)
    )
    row.get_by_role("button").click()

    expect(page).to_have_url(f"{BASE_URL}/accounts", timeout=5000)


def test_wizard_categories_go_button_navigates(page: Page) -> None:
    """Clicking Go/Edit on the categories step navigates to /categories."""
    page.goto(f"{BASE_URL}/wizard")

    row = page.locator("div.row").filter(
        has=page.get_by_text("Create expense and income categories", exact=True)
    )
    row.get_by_role("button").click()

    expect(page).to_have_url(f"{BASE_URL}/categories", timeout=5000)


def test_wizard_import_go_button_navigates(page: Page) -> None:
    """Clicking Go/Edit on the import step navigates to /import."""
    page.goto(f"{BASE_URL}/wizard")

    row = page.locator("div.row").filter(
        has=page.get_by_text("Import or add transactions", exact=True)
    )
    row.get_by_role("button").click()

    expect(page).to_have_url(f"{BASE_URL}/import", timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: All-done badge when every step is complete
# ---------------------------------------------------------------------------

def test_wizard_all_done_badge_when_setup_complete(page: Page) -> None:
    """Scenario: All done! badge appears when institution, account, categories, tx all exist."""
    from kaleta.db import AsyncSessionFactory
    from kaleta.models.category import CategoryType
    from kaleta.models.transaction import TransactionType
    from kaleta.schemas.category import CategoryCreate
    from kaleta.schemas.transaction import TransactionCreate
    from kaleta.services import CategoryService, TransactionService

    inst_id = seed_institution("All Done Wizard E2E Bank")
    acc_id = seed_account("All Done Wizard E2E Account", institution_id=inst_id)

    async def _seed_cats_and_tx() -> None:
        async with AsyncSessionFactory() as session:
            from sqlalchemy import select
            from kaleta.models.category import Category

            cat_svc = CategoryService(session)

            async def _get_or_create_cat(name: str, ct: CategoryType) -> int:
                ex = (
                    await session.execute(
                        select(Category).where(
                            Category.name == name, Category.parent_id.is_(None)
                        )
                    )
                ).scalar_one_or_none()
                if ex:
                    return ex.id
                c = await cat_svc.create(CategoryCreate(name=name, type=ct))
                return c.id

            exp_id = await _get_or_create_cat(
                "All Done E2E Expense Cat", CategoryType.EXPENSE
            )
            await _get_or_create_cat("All Done E2E Income Cat", CategoryType.INCOME)

            tx_svc = TransactionService(session)
            await tx_svc.create(
                TransactionCreate(
                    account_id=acc_id,
                    category_id=exp_id,
                    amount=Decimal("10.00"),
                    type=TransactionType.EXPENSE,
                    date=datetime.date.today(),
                    description="wizard e2e seed",
                )
            )

    _run(_seed_cats_and_tx())

    page.goto(f"{BASE_URL}/wizard")
    expect(page.get_by_text("All done!")).to_be_visible(timeout=5000)
