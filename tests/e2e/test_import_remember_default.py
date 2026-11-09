# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: "Remember this mapping" for an mBank statement of a registered account.

Covers: KAL-CSV-041

mBank names a statement ``<last 8 account digits>_<from>_<to>.csv``. When the
statement's account number matches a registered account, the account is chosen
by that number, so "Remember this mapping" starts unticked; ticked, it suggests
a pattern that keeps the account digits and drops the dates.
Page URL: /import (Settings step)
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account_with_external

STATEMENT = Path(__file__).resolve().parent / "fixtures" / "import" / "44440393_261011_261109.csv"
ACCOUNT = "AAA mBank CSV041 E2E"


def test_remember_mapping_unticked_for_an_account_matched_by_number(
    page: Page, base_url: str
) -> None:
    """Covers: KAL-CSV-041"""
    seed_account_with_external(ACCOUNT, "55114020040000330244440393")

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(STATEMENT))
    expect(page.locator("[data-page-eyebrow]")).to_contain_text(STATEMENT.name, timeout=10000)
    page.keyboard.press("Escape")
    page.locator('[data-step="4"]').click()
    expect(page.locator('[data-step-panel="4"]')).to_be_visible(timeout=5000)

    # Matched by the statement's own number...
    expect(page.locator(".q-select").filter(has_text="Target account")).to_contain_text(
        ACCOUNT, timeout=5000
    )
    # ...so the box starts unticked, and the pattern field it reveals is hidden.
    remember = page.get_by_role("checkbox", name="Remember this mapping")
    expect(remember).to_have_attribute("aria-checked", "false")
    pattern = page.get_by_label("Filename pattern", exact=True)
    expect(pattern).to_be_hidden()

    # Ticked by hand, the suggestion keeps the account digits, not the dates.
    remember.click()
    expect(remember).to_have_attribute("aria-checked", "true")
    expect(pattern).to_have_value("44440393_*_*.csv")
