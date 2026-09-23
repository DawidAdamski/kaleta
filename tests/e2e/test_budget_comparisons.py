# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Budget Planning Comparisons.

Page URL: /budget-plan
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import list_budgets, seed_budget, seed_category

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
