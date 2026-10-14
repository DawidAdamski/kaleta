# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test: Settings sets the ledger's default page size and grouping.

Covers: KAL-SET-032
Page URL: /settings, /transactions
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_ledger_opens_on_the_settings_page_size_and_grouping(page: Page, base_url: str) -> None:
    """Covers: KAL-SET-032

    The "Transactions list" settings card picks the rows-per-page and grouping
    the ledger opens on. The ledger's own selector and toggle still override
    within a session.
    """
    page.goto(f"{base_url}/settings?tab=features")

    # On the features tab, "200" is unique to the ledger page-size toggle and
    # "Month" to the ledger grouping toggle (other prefs are number inputs or
    # different values), so the labels locate each toggle option on their own.
    page_size_200 = page.get_by_role("button", name="200", exact=True)
    expect(page_size_200).to_be_visible(timeout=10000)
    page_size_200.click()
    page.get_by_role("button", name="Month", exact=True).click()

    try:
        page.goto(f"{base_url}/transactions")
        # The page-size select (the only select in the ledger footer) opens on 200.
        expect(page.locator(".k-ledger-foot .q-select")).to_contain_text("200", timeout=10000)
        # The grouping segment opens on Month (Quasar marks the active option).
        expect(page.locator(".k-segment button.bg-primary")).to_have_text("Month")
    finally:
        # Left as found: this pref is shared across the suite's one session, so
        # every other ledger test reads the default 50 rows / no grouping.
        page.goto(f"{base_url}/settings?tab=features")
        page.get_by_role("button", name="50", exact=True).click()
        page.get_by_role("button", name="None", exact=True).click()
