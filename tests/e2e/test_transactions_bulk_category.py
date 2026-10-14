# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test for Feature: Manual Transaction Entry — bulk change category.

Covers: KAL-TXN-022
Page URL: /transactions

Dogfooding #17: the ledger gained multi-select but no way to recategorise a
batch. Selecting several rows of one type and picking a category reassigns
them all in one step.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.ledger import filter_ledger_by_account
from tests.e2e.seed_helpers import seed_account, seed_category, seed_transaction


def test_bulk_assign_category_to_selected_rows(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-022

    Select three expense rows sharing one category and reassign them to another
    expense category through the selection bar's "Change category" action.
    """
    account_name = "Bulk Cat Tx E2E"
    old_cat = "Bulk Old Cat E2E"
    new_cat = "Bulk New Cat E2E"
    account_id = seed_account(account_name)
    old_cat_id = seed_category(old_cat)
    seed_category(new_cat)

    for i in range(3):
        seed_transaction(account_id, old_cat_id, 10.0 + i, description=f"BulkCat {i:02d}")

    page.goto(f"{base_url}/transactions")
    filter_ledger_by_account(page, account_name)

    # Tick all three rows.
    for i in range(3):
        row = page.locator(".q-table tbody tr").filter(has_text=f"BulkCat {i:02d}")
        expect(row).to_have_count(1, timeout=10000)
        row.get_by_role("checkbox").click()

    # The selection bar offers "Change category" once rows are ticked.
    page.get_by_role("button", name="Change category", exact=True).click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_label("Category").click()
    page.locator(".q-menu").get_by_text(new_cat, exact=True).click()
    dialog.get_by_role("button", name="Assign", exact=True).click()

    # Every selected row now reads the new category; the ledger stays in place.
    for i in range(3):
        row = page.locator(".q-table tbody tr").filter(has_text=f"BulkCat {i:02d}")
        expect(row.get_by_text(new_cat, exact=True)).to_be_visible(timeout=10000)
