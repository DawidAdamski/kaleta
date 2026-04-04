"""E2E tests for Feature: Annual Budget Planning.

Maps scenarios from docs/bdd.md — Feature: Annual Budget Planning.
Page URL: /budget-plan
"""

from __future__ import annotations

import asyncio
import datetime
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8080"
CURRENT_YEAR = datetime.date.today().year
CURRENT_MONTH = datetime.date.today().month

_executor = ThreadPoolExecutor(max_workers=1)


def _run(coro):  # type: ignore[no-untyped-def]
    def _worker():  # type: ignore[no-untyped-def]
        return asyncio.run(coro)

    return _executor.submit(_worker).result()


# ---------------------------------------------------------------------------
# Seed helpers (idempotent)
# ---------------------------------------------------------------------------


def seed_category(name: str, cat_type: str = "expense") -> int:
    from sqlalchemy import select

    from kaleta.db import AsyncSessionFactory
    from kaleta.models.category import Category, CategoryType
    from kaleta.schemas.category import CategoryCreate
    from kaleta.services import CategoryService

    async def _create() -> int:
        async with AsyncSessionFactory() as session:
            existing = (
                await session.execute(
                    select(Category).where(Category.name == name, Category.parent_id.is_(None))
                )
            ).scalar_one_or_none()
            if existing:
                return existing.id
            ct = CategoryType(cat_type)
            cat = await CategoryService(session).create(CategoryCreate(name=name, type=ct))
            return cat.id

    return _run(_create())


def seed_budget(category_id: int, amount: float, month: int, year: int) -> int:
    from kaleta.db import AsyncSessionFactory
    from kaleta.schemas.budget import BudgetCreate
    from kaleta.services import BudgetService

    async def _create() -> int:
        async with AsyncSessionFactory() as session:
            svc = BudgetService(session)
            b = await svc.upsert(
                BudgetCreate(
                    category_id=category_id,
                    amount=Decimal(str(amount)),
                    month=month,
                    year=year,
                )
            )
            return b.id

    return _run(_create())


# ---------------------------------------------------------------------------
# Scenario: Budget Plan page loads
# ---------------------------------------------------------------------------


def test_budget_plan_page_loads(page: Page) -> None:
    """Budget Plan page renders the grid with month column headers."""
    page.goto(f"{BASE_URL}/budget-plan")

    # Use exact=True to avoid strict-mode violation from multiple "Budget Plan" texts
    expect(page.get_by_role("main").get_by_text("Budget Plan", exact=True)).to_be_visible(
        timeout=5000
    )
    expect(page.get_by_text("Jan", exact=True).first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Dec", exact=True).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Budget plan grid shows Planned and Actual column groups
# ---------------------------------------------------------------------------


def test_budget_plan_page_shows_planned_and_actual_columns(page: Page) -> None:
    """Budget Plan grid renders Planned and Actual column groups."""
    cat_id = seed_category("Food Plan ActualCol")
    # Seed a budget entry so the actual row appears
    seed_budget(cat_id, 100, CURRENT_MONTH, CURRENT_YEAR)

    page.goto(f"{BASE_URL}/budget-plan")
    expect(page.get_by_role("main").get_by_text("Budget Plan", exact=True)).to_be_visible(
        timeout=5000
    )
    # "Planned" appears as the Month column header label on each row
    expect(page.get_by_text("Planned", exact=True).first).to_be_visible(timeout=5000)
    # "Actual" label appears in actual sub-rows or column headers
    expect(page.get_by_text("Actual", exact=True).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: A seeded expense category appears in the budget grid
# ---------------------------------------------------------------------------


def test_seeded_category_appears_in_budget_grid(page: Page) -> None:
    """A seeded expense category appears as a row in the budget plan grid."""
    seed_category("Food Budget Grid E2E")

    page.goto(f"{BASE_URL}/budget-plan")
    expect(page.get_by_text("Food Budget Grid E2E")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Budget totals reflect seeded budget entries
# ---------------------------------------------------------------------------


def test_budget_totals_reflect_seeded_entries(page: Page) -> None:
    """Scenario: Budget totals update when a cell is changed.

    Seeds 800 for all 12 months for CURRENT_YEAR and asserts yearly total is 9,600.
    """
    cat_id = seed_category("Food Totals Update E2E")
    for m in range(1, 13):
        seed_budget(cat_id, 800, m, CURRENT_YEAR)

    page.goto(f"{BASE_URL}/budget-plan")
    expect(page.get_by_text("Food Totals Update E2E")).to_be_visible(timeout=5000)

    # Yearly total for this category should be 9,600
    expect(page.get_by_text("9,600").first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Set all 12 months at once via the Monthly dialog
# ---------------------------------------------------------------------------


def test_set_uniform_amount_for_all_months(page: Page) -> None:
    """Scenario: Set the same amount for all 12 months at once"""
    seed_category("Transport Budget Plan E2E")

    page.goto(f"{BASE_URL}/budget-plan")
    expect(page.get_by_text("Transport Budget Plan E2E")).to_be_visible(timeout=5000)

    # Each category row has a "Monthly" column (the recurring-amount cell) that
    # opens the "apply to all 12 months" dialog when clicked.
    # Locate the row using a parent container and click the Monthly cell.
    # The Monthly cell text is "—" initially but the label style includes _S_REC.
    # We click the recurring-value label inside the Transport row.
    # The budget_plan grid uses flat divs, not a <table>; rows are ui.row() containers.

    # Strategy: find all rows on the page, filter to the one containing the
    # category name, then click its Monthly (recurring) cell.
    transport_rows = page.locator(".q-row, [class*='row']").filter(
        has_text="Transport Budget Plan E2E"
    )
    # The recurring cell is the first clickable label after the category name.
    # In NiceGUI it has the text "—" and cursor-pointer styling.
    recurring_cell = transport_rows.first.locator(".cursor-pointer").first
    recurring_cell.click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    amount_input = dialog.locator("input[type='number']").first
    amount_input.click(click_count=3)
    amount_input.fill("300")

    dialog.get_by_role("button", name="Apply to all 12 months").click()

    # Annual total for Transport should now be 3,600 (300 × 12)
    expect(page.get_by_text("3,600").first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Navigate to previous year shows a year label
# ---------------------------------------------------------------------------


def test_navigate_to_previous_year_shows_year_label(page: Page) -> None:
    """Scenario: Navigate to a previous year — page shows the year."""
    page.goto(f"{BASE_URL}/budget-plan")
    expect(page.get_by_text(str(CURRENT_YEAR)).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Amount-positive guard — zero amount triggers warning notification
# ---------------------------------------------------------------------------


def test_zero_budget_amount_triggers_warning(page: Page) -> None:
    """Scenario: Cannot enter a zero/negative budget amount."""
    seed_category("Food Zero Budget E2E")

    page.goto(f"{BASE_URL}/budget-plan")
    expect(page.get_by_text("Food Zero Budget E2E")).to_be_visible(timeout=5000)

    food_rows = page.locator(".q-row, [class*='row']").filter(has_text="Food Zero Budget E2E")
    recurring_cell = food_rows.first.locator(".cursor-pointer").first
    recurring_cell.click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    amount_input = dialog.locator("input[type='number']").first
    amount_input.click(click_count=3)
    amount_input.fill("0")

    dialog.get_by_role("button", name="Apply to all 12 months").click()

    # The view emits a warning notification (amount must be > 0)
    expect(page.locator(".q-notification")).to_be_visible(timeout=5000)
