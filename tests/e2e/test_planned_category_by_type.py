# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E for Feature: Planned and Recurring Transactions — category by type.

Covers: KAL-PLN-028

The Add/Edit planned dialog listed every category regardless of the chosen
type, so an expense plan offered income categories and vice versa. Selecting
a type must narrow the category list to that type (and offer none for a
transfer). Cross-type categories are removed from the select's option model
entirely, so their absence is asserted with a zero count.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.ledger import pick_open_menu_option
from tests.e2e.seed_helpers import seed_account, seed_category


def test_planned_category_list_narrows_by_type(page: Page, base_url: str) -> None:
    """Covers: KAL-PLN-028"""
    seed_account("Planned Main Acct")
    seed_category("E2E Planned Expense Cat", cat_type="expense")
    seed_category("E2E Planned Income Cat", cat_type="income")

    page.goto(f"{base_url}/planned")
    page.get_by_role("button", name="Add Planned").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    cat_select = dialog.locator(".q-select").filter(has_text="Category")
    type_select = dialog.locator(".q-select").filter(has_text="Type")

    # Default type is Expense: the income category is not even in the options.
    cat_select.click()
    menu = page.locator(".q-menu").last
    expect(menu).to_be_visible(timeout=3000)
    expect(menu.get_by_text("E2E Planned Income Cat", exact=True)).to_have_count(0)
    pick_open_menu_option(page, "E2E Planned Expense Cat")  # present → selectable

    # Switch to Income — the category selection is cleared and the list swaps.
    type_select.click()
    pick_open_menu_option(page, "Income")

    cat_select.click()
    menu = page.locator(".q-menu").last
    expect(menu).to_be_visible(timeout=3000)
    expect(menu.get_by_text("E2E Planned Expense Cat", exact=True)).to_have_count(0)
    pick_open_menu_option(page, "E2E Planned Income Cat")  # present → selectable
