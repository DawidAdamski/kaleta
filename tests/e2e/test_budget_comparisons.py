# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Budget Planning Comparisons.

Page URL: /budget-plan
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from playwright.sync_api import Locator, Page, expect

from tests.e2e.seed_helpers import (
    list_budgets,
    seed_account,
    seed_budget,
    seed_category,
    seed_transaction,
)

CURRENT_YEAR = datetime.date.today().year
# The toolbar's copy target defaults to this month (February at the
# earliest, so that "previous month" stays inside the edited year).
TARGET_MONTH = max(datetime.date.today().month, 2)
SOURCE_MONTH = TARGET_MONTH - 1


def _set_cell(page: Page, category: str, month: int, amount: str) -> None:
    row = page.locator(".k-plan-row").filter(has_text=category).first
    row.locator(".k-plan-cell").nth(month - 1).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    field = dialog.locator("input[type='number']").first
    field.click(click_count=3)
    field.fill(amount)
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_be_hidden(timeout=5000)


def test_copy_previous_month_then_adjust_two_categories(page: Page, base_url: str) -> None:
    """Covers: KAL-CMP-003

    Last month has a saved plan; copying it into this month and adjusting
    two category amounts saves the new plan with those adjustments, and
    the untouched category keeps last month's amount.
    """
    food = seed_category("Food CMP E2E")
    transport = seed_category("Transport CMP E2E")
    fun = seed_category("Fun CMP E2E")
    seed_budget(food, 800.0, SOURCE_MONTH, CURRENT_YEAR)
    seed_budget(transport, 300.0, SOURCE_MONTH, CURRENT_YEAR)
    seed_budget(fun, 100.0, SOURCE_MONTH, CURRENT_YEAR)

    page.goto(f"{base_url}/budget-plan")
    expect(page.get_by_text("Food CMP E2E").first).to_be_visible(timeout=10000)

    page.get_by_role("button", name="Copy from previous month").click()
    expect(page.get_by_text("categories copied forward").first).to_be_visible(timeout=5000)

    _set_cell(page, "Food CMP E2E", TARGET_MONTH, "850")
    _set_cell(page, "Transport CMP E2E", TARGET_MONTH, "250")

    budgets = list_budgets(CURRENT_YEAR, TARGET_MONTH)
    saved = {b["category_id"]: Decimal(str(b["amount"])) for b in budgets}
    assert saved.get(food) == Decimal("850")
    assert saved.get(transport) == Decimal("250")
    assert saved.get(fun) == Decimal("100")


def _actual_cell(page: Page, category: str, month: int) -> Locator:
    """The month's cell on the category's actual line (label, Dec slot, then Jan…Dec)."""
    row = page.locator(".k-plan-row").filter(has_text=category).first
    return row.locator(".k-plan-actual > *").nth(1 + month)


def test_previous_month_actual_sits_beside_the_month_being_planned(
    page: Page, base_url: str
) -> None:
    """Covers: KAL-CMP-001

    Last month's spending is on the category row, and January — whose
    previous month is last year's December — shows that December too.
    """
    category = "Food Prev Month CMP E2E"
    account = seed_account("Prev Month CMP E2E")
    cat_id = seed_category(category)
    seed_budget(cat_id, 500.0, TARGET_MONTH, CURRENT_YEAR)
    seed_transaction(account, cat_id, 420.0, date=datetime.date(CURRENT_YEAR - 1, 12, 14))
    seed_transaction(account, cat_id, 365.0, date=datetime.date(CURRENT_YEAR, SOURCE_MONTH, 10))

    page.goto(f"{base_url}/budget-plan")
    row = page.locator(".k-plan-row").filter(has_text=category).first
    expect(row).to_be_visible(timeout=10000)

    expect(_actual_cell(page, category, SOURCE_MONTH)).to_have_text("365")
    december = row.locator("[data-prev-december]")
    expect(december).to_have_text(f"Dec ’{(CURRENT_YEAR - 1) % 100:02d} 420")


def test_plan_this_year_while_seeing_the_same_month_in_past_years(
    page: Page, base_url: str
) -> None:
    """Covers: KAL-CMP-002

    With July of the two previous years chosen as reference, their actuals
    sit under the category, and July of this year can still be planned.
    """
    category = "Food July CMP E2E"
    account = seed_account("July CMP E2E")
    cat_id = seed_category(category)
    two_back, one_back = CURRENT_YEAR - 2, CURRENT_YEAR - 1
    for year in (two_back, one_back):
        seed_budget(cat_id, 300.0, 7, year)
    seed_transaction(account, cat_id, 310.0, date=datetime.date(two_back, 7, 5))
    seed_transaction(account, cat_id, 355.0, date=datetime.date(one_back, 7, 5))

    page.goto(f"{base_url}/budget-plan")
    row = page.locator(".k-plan-row").filter(has_text=category).first
    expect(row).to_be_visible(timeout=10000)
    expect(row.locator(".k-plan-ref")).to_have_count(0)

    page.get_by_role("button", name=str(two_back), exact=True).click()
    page.get_by_role("button", name=str(one_back), exact=True).click()

    for year, spent in ((two_back, "310"), (one_back, "355")):
        reference = row.locator(f"[data-reference-year='{year}']")
        expect(reference).to_be_visible(timeout=5000)
        expect(reference).to_contain_text(f"actual {year}")
        # label, empty Month slot, then January…December.
        expect(reference.locator(":scope > *").nth(1 + 7)).to_have_text(spent)

    _set_cell(page, category, 7, "380")
    saved = {b["category_id"]: Decimal(str(b["amount"])) for b in list_budgets(CURRENT_YEAR, 7)}
    assert saved.get(cat_id) == Decimal("380")
