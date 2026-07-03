"""E2E tests for Feature: Settings — Data safety.

Covers: KAL-SET-013

Page URL: /settings (Data tab)
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account


def test_wipe_requires_delete_confirmation(page: Page, base_url: str) -> None:
    """Covers: KAL-SET-013

    Opening the wipe dialog keeps the confirm button disabled until DELETE
    is typed exactly; wrong text leaves data intact.
    """
    account_name = "Data Safety E2E"
    seed_account(account_name)

    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="Data").click()
    page.get_by_role("button", name="Clear all data").click()

    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Clear all data?", exact=True)).to_be_visible(timeout=5000)

    confirm_btn = dialog.get_by_role("button", name="Clear all data")
    expect(confirm_btn).to_be_disabled()

    dialog.get_by_label("Type DELETE to confirm").fill("delete")
    expect(confirm_btn).to_be_disabled()

    dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).not_to_be_visible(timeout=5000)

    page.goto(f"{base_url}/accounts")
    expect(page.get_by_text(account_name, exact=True)).to_be_visible(timeout=5000)
