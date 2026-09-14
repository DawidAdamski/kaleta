# SPDX-License-Identifier: AGPL-3.0-or-later
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

    over_name = "Fuel Budget Actual E2E"
    over_cat = seed_category(over_name)
    seed_budget(over_cat, 100.0, CURRENT_MONTH, CURRENT_YEAR)
    seed_transaction(acc_id, over_cat, 260.0, description="Orlen Budget Actual E2E")

    page.goto(f"{base_url}/budget-plan")
    expect(page.get_by_text(category_name)).to_be_visible(timeout=5000)

    # Both figures are on the row: the plan on the category line, what was
    # spent on the actual line under it.
    category_row = page.locator(".k-plan-row").filter(has_text=category_name).first
    expect(category_row.get_by_text(f"{planned:,.0f}").first).to_be_visible(timeout=5000)
    under_actual = category_row.locator(".k-plan-actual")
    expect(under_actual.get_by_text(f"{spent:,.0f}").first).to_be_visible(timeout=5000)

    # Artboard 2c keeps the sub-row quiet: only an overspent month is
    # coloured. A year of ordinary months used to come out as a wall of green
    # saying "you spent money", which is what a ledger always says.
    assert spent <= planned
    expect(under_actual.locator(".k-amount--out")).to_have_count(0)

    # And the overspent category, seeded alongside, does take the colour —
    # the half of the rule a single under-budget row cannot show.
    over_row = page.locator(".k-plan-row").filter(has_text=over_name).first
    expect(over_row.locator(".k-plan-actual .k-amount--out").first).to_be_visible(timeout=5000)

    expect(page.get_by_text(CURRENT_MONTH_LABEL, exact=True).first).to_be_visible(timeout=5000)
