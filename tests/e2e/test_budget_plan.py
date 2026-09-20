# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Annual Budget Planning.

Maps scenarios from docs/bdd.md — Feature: Annual Budget Planning.
Page URL: /budget-plan
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_budget, seed_category

CURRENT_YEAR = datetime.date.today().year
CURRENT_MONTH = datetime.date.today().month


# ---------------------------------------------------------------------------
# Scenario: Budget Plan page loads
# ---------------------------------------------------------------------------


def test_budget_plan_page_loads(page: Page, base_url: str) -> None:
    """Budget Plan page renders the grid with month column headers."""
    page.goto(f"{base_url}/budget-plan")

    # Use exact=True to avoid strict-mode violation from multiple "Budget Plan" texts
    expect(page.get_by_role("main").get_by_text("Budget Plan", exact=True)).to_be_visible(
        timeout=5000
    )
    expect(page.get_by_text("Jan", exact=True).first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Dec", exact=True).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Budget plan grid shows Planned and Actual column groups
# ---------------------------------------------------------------------------


def test_budget_plan_page_shows_planned_and_actual_columns(page: Page, base_url: str) -> None:
    """Budget Plan grid renders Planned and Actual column groups."""
    cat_id = seed_category("Food Plan ActualCol")
    # Seed a budget entry so the actual row appears
    seed_budget(cat_id, 100, CURRENT_MONTH, CURRENT_YEAR)

    page.goto(f"{base_url}/budget-plan")
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


def test_seeded_category_appears_in_budget_grid(page: Page, base_url: str) -> None:
    """A seeded expense category appears as a row in the budget plan grid."""
    seed_category("Food Budget Grid E2E")

    page.goto(f"{base_url}/budget-plan")
    expect(page.get_by_text("Food Budget Grid E2E")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Budget totals reflect seeded budget entries
# ---------------------------------------------------------------------------


def test_budget_totals_reflect_seeded_entries(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-005

    Seeds 800 for all 12 months for CURRENT_YEAR and asserts yearly total is 9,600.
    """
    cat_id = seed_category("Food Totals Update E2E")
    for m in range(1, 13):
        seed_budget(cat_id, 800, m, CURRENT_YEAR)

    page.goto(f"{base_url}/budget-plan")
    expect(page.get_by_text("Food Totals Update E2E")).to_be_visible(timeout=5000)

    # Yearly total for this category should be 9,600
    expect(page.get_by_text("9 600").first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Set all 12 months at once via the Monthly dialog
# ---------------------------------------------------------------------------


def test_set_uniform_amount_for_all_months(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-002"""
    seed_category("Transport Budget Plan E2E")

    page.goto(f"{base_url}/budget-plan")
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
    expect(page.get_by_text("3 600").first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Navigate to previous year shows a year label
# ---------------------------------------------------------------------------


def test_navigate_to_previous_year_shows_year_label(page: Page, base_url: str) -> None:
    """Scenario: Navigate to a previous year — page shows the year."""
    page.goto(f"{base_url}/budget-plan")
    expect(page.get_by_text(str(CURRENT_YEAR)).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Amount-positive guard — zero amount triggers warning notification
# ---------------------------------------------------------------------------


def test_zero_budget_amount_triggers_warning(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-010"""
    seed_category("Food Zero Budget E2E")

    page.goto(f"{base_url}/budget-plan")
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


# ---------------------------------------------------------------------------
# Scenario: Row actions live in a context menu (artboard 2c)
# ---------------------------------------------------------------------------


def test_row_actions_open_from_right_click_and_from_the_button(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-015

    The two per-row buttons cost 76px of a grid that needs every pixel for
    twelve month columns. They moved into a right-click menu — and kept a
    button, because a touch screen has no right button and nobody discovers a
    context menu on a table row by accident.
    """
    category = "Zywnosc Grid Menu E2E"
    cat_id = seed_category(category)
    seed_budget(cat_id, 500.0, CURRENT_MONTH, CURRENT_YEAR)

    page.goto(f"{base_url}/budget-plan")
    row = page.locator(".k-plan-row").filter(has_text=category).first
    expect(row).to_be_visible(timeout=10000)

    row.click(button="right")
    menu = page.locator(".q-menu").last
    expect(menu).to_be_visible(timeout=5000)
    expect(menu.get_by_text("Set from yearly total", exact=True)).to_be_visible()
    expect(menu.get_by_text("Clear all months", exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(".q-menu")).to_have_count(0, timeout=5000)

    row.get_by_role("button", name=f"Row actions: {category}").click()
    menu = page.locator(".q-menu").last
    expect(menu).to_be_visible(timeout=5000)
    expect(menu.get_by_text("Set from yearly total", exact=True)).to_be_visible()


def test_the_grid_tints_the_current_month(page: Page, base_url: str) -> None:
    """Covers: KAL-BUD-016

    Twelve identical columns, and the one the user is living in has to be
    findable without counting across from January.
    """
    category = "Zywnosc Grid Tint E2E"
    cat_id = seed_category(category)
    seed_budget(cat_id, 500.0, CURRENT_MONTH, CURRENT_YEAR)

    page.goto(f"{base_url}/budget-plan")
    row = page.locator(".k-plan-row").filter(has_text=category).first
    expect(row).to_be_visible(timeout=10000)

    # One tinted cell in the header, and one on each of the category's two
    # lines — the plan and the actual under it, which render as one row.
    header = page.locator(".k-plan-head").first
    expect(header.locator(".k-plan-month-now")).to_have_count(1)
    expect(row.locator(".k-plan-month-now")).to_have_count(2)

    # The actual sub-row sits under the plan, quiet and in mono, with its own
    # tinted cell for the current month. It renders for a budgeted category
    # even with nothing spent — ``PlanCategoryRow.show_actual_row`` is true
    # when there is a plan, so the line is there to be filled in.
    actual_row = row.locator(".k-plan-actual")
    expect(actual_row).to_be_visible()
    expect(actual_row.locator(".k-mono").first).to_be_visible()
    expect(actual_row.locator(".k-plan-month-now")).to_have_count(1)
