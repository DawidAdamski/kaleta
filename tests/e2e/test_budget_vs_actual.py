"""E2E tests for Feature: Annual Budget Planning — budget vs actual view.

Covers: KAL-BUD-006

Maps the q3-test-safety-net budget execution flow.
Page URL: /budget-plan
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_budget, seed_category, seed_transaction

CURRENT_YEAR = datetime.date.today().year
CURRENT_MONTH = datetime.date.today().month
_MONTH_LABELS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
CURRENT_MONTH_LABEL = _MONTH_LABELS[CURRENT_MONTH - 1]


def test_budget_vs_actual_shows_planned_and_spent(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-006"""
    category_name = "Food Budget Actual E2E"
    account_name = "PKO Budget Actual E2E"
    tx_description = "Groceries Budget Actual E2E"
    planned = 800.0
    spent = 450.0

    cat_id = seed_category(category_name)
    acc_id = seed_account(account_name)
    seed_budget(cat_id, planned, CURRENT_MONTH, CURRENT_YEAR)
    seed_transaction(
        acc_id,
        cat_id,
        spent,
        description=tx_description,
    )

    page.goto(f"{base_url}/budget-plan")
    expect(page.get_by_text(category_name)).to_be_visible(timeout=5000)

    category_row = page.locator("div").filter(has_text=category_name).first
    expect(category_row.get_by_text(f"{planned:,.0f}").first).to_be_visible(timeout=5000)

    actual_row = page.locator("div").filter(has_text="Actual").filter(
        has_text=f"{spent:,.0f}"
    ).first
    expect(actual_row).to_be_visible(timeout=5000)

    if spent <= planned:
        expect(actual_row.locator(".text-green-6").first).to_be_visible(timeout=5000)
    else:
        expect(actual_row.locator(".text-red-6").first).to_be_visible(timeout=5000)

    expect(page.get_by_text(CURRENT_MONTH_LABEL, exact=True).first).to_be_visible(timeout=5000)
