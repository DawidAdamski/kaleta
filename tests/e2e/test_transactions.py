# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Manual Transaction Entry.

Covers: KAL-TXN-001

Maps the q3-test-safety-net flow: add, edit, and split a transaction.
Page URL: /transactions
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_category


def _fill_number(scope: Page, label: str, value: str) -> None:
    field = scope.get_by_role("spinbutton", name=label, exact=True)
    field.click(click_count=3)
    field.fill(value)


def _select_option(page: Page, dialog: Page, select_index: int, option: str) -> None:
    dialog.locator(".q-select").nth(select_index).click()
    page.locator(".q-menu").get_by_text(option, exact=True).click()


def test_add_edit_split_transaction(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-001

    Exercises the full manual-entry flow — add an expense, edit its
    description and amount, then create a split transaction across two
    categories (split UI; no separate BDD scenario).
    """
    account_name = "PKO Main Tx E2E"
    food_cat = "Food Tx E2E"
    split_cat_a = "Food Split A Tx E2E"
    split_cat_b = "Food Split B Tx E2E"

    seed_account(account_name)
    seed_category(food_cat)
    seed_category(split_cat_a)
    seed_category(split_cat_b)

    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    # ── Add expense ───────────────────────────────────────────────────────
    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "45.50")
    dialog.get_by_label("Description (optional)").fill("Supermarket Tx E2E")
    dialog.get_by_label("Category").click()
    page.locator(".q-menu").get_by_text(food_cat, exact=True).click()
    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Supermarket Tx E2E").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("-45.50").first).to_be_visible(timeout=5000)

    # ── Edit ──────────────────────────────────────────────────────────────
    row = page.locator(".q-table tbody tr").filter(has_text="Supermarket Tx E2E")
    row.get_by_role("button").first.click()

    edit_dialog = page.get_by_role("dialog")
    expect(edit_dialog.get_by_text("Edit Transaction", exact=True)).to_be_visible(timeout=5000)

    desc_field = edit_dialog.get_by_label("Description (optional)")
    desc_field.click(click_count=3)
    desc_field.fill("Supermarket Updated Tx E2E")
    _fill_number(edit_dialog, "Amount", "50.00")
    edit_dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Supermarket Updated Tx E2E").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("-50.00").first).to_be_visible(timeout=5000)

    # ── Split ─────────────────────────────────────────────────────────────
    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "100")
    dialog.get_by_label("Description (optional)").fill("Split Grocery Tx E2E")
    dialog.get_by_text("Split", exact=True).click()

    split_rows = dialog.locator(".split-cat-select")
    expect(split_rows).to_have_count(2, timeout=5000)

    split_rows.nth(0).click()
    page.locator(".q-menu").get_by_text(split_cat_a, exact=True).click()
    split_rows.nth(1).click()
    page.locator(".q-menu").get_by_text(split_cat_b, exact=True).click()

    split_amount_fields = dialog.locator(".split-cat-select").locator(
        "xpath=ancestor::div[contains(@class,'row')][1]//input[@type='number']"
    )
    split_amount_fields.first.click(click_count=3)
    split_amount_fields.first.fill("60")
    dialog.get_by_role("button", name="Fill last").click()

    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Split Grocery Tx E2E").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("-100.00").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("(Split:", exact=False).first).to_be_visible(timeout=5000)
