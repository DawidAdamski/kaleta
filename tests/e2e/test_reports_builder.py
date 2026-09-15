# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Report Builder.

Maps scenarios from docs/bdd.md — Feature: Report Builder.
Page URL: /reports/builder
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

from tests.e2e import seed_helpers as sh

BUILDER = "/reports/builder"
REPORT_NAME = "Spend by account E2E"


def _slots(page: Page) -> Locator:
    """The five clickable parts of the sentence, in reading order."""
    return page.locator(".k-slot")


def _slot_text(page: Page, index: int) -> str:
    # Each slot carries its label and an expand_more glyph; the label is the
    # first line of it.
    return _slots(page).nth(index).inner_text().split("\n")[0].strip()


def _pick(page: Page, slot_index: int, option: str) -> None:
    _slots(page).nth(slot_index).click()
    menu = page.locator(".q-menu:visible")
    expect(menu).to_be_visible(timeout=5000)
    menu.locator(".q-item").filter(has_text=option).first.click()


def test_sentence_reflects_state_and_a_saved_report_comes_back(page: Page, base_url: str) -> None:
    """Covers: KAL-RPT-001

    The sentence is the builder's only statement of what it is about to ask,
    so it has to follow the state both ways: when the user edits it, and when
    a saved report puts state back underneath it.
    """
    account_id = sh.seed_account("Reports Builder E2E Account")
    category_id = sh.seed_category("Reports Builder E2E Category")
    sh.seed_transaction(account_id, category_id, 120.0, description="reports builder e2e")

    page.goto(f"{base_url}{BUILDER}")
    expect(page.get_by_text("Unsaved report")).to_be_visible(timeout=10000)

    # The defaults, read off the page rather than assumed.
    expect(_slots(page)).to_have_count(5)
    assert _slot_text(page, 0) == "Total Amount"
    assert _slot_text(page, 1) == "Category"
    assert _slot_text(page, 2) == "Expense"
    assert _slot_text(page, 3) == "This Year"
    assert _slot_text(page, 4) == "10"

    # Editing a slot changes the query it describes.
    _pick(page, 1, "Account")
    expect(_slots(page).nth(1)).to_contain_text("Account", timeout=5000)

    page.get_by_role("button", name="Run").click()
    expect(page.get_by_text("by Account", exact=False).first).to_be_visible(timeout=10000)

    # Save it, then come back to a builder that knows nothing.
    page.get_by_role("button", name="Save report").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_label("Report Name").fill(REPORT_NAME)
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Report saved", exact=False).first).to_be_visible(timeout=10000)

    page.goto(f"{base_url}{BUILDER}")
    expect(page.get_by_text("Unsaved report")).to_be_visible(timeout=10000)
    assert _slot_text(page, 1) == "Category", "a fresh builder starts from the defaults"

    page.get_by_text(REPORT_NAME, exact=True).click()

    # The saved state comes back through the same sentence that wrote it.
    expect(_slots(page).nth(1)).to_contain_text("Account", timeout=10000)
    expect(page.get_by_text(REPORT_NAME, exact=True).first).to_be_visible()
