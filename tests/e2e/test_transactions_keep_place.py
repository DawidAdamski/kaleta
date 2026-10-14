# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test for Feature: Manual Transaction Entry — editing keeps your place.

Covers: KAL-TXN-021
Page URL: /transactions

Dogfooding bug #22: saving a change to an existing transaction re-read the
ledger and snapped it back to page 1 at the top. This pins the deterministic
half of the fix — editing a row shown on page 2 leaves the ledger on page 2.
(Scroll-offset restore is best-effort cosmetics and timing-dependent, so it
is not asserted here.)
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.ledger import filter_ledger_by_account
from tests.e2e.seed_helpers import seed_account, seed_category, seed_transaction


def test_editing_a_row_keeps_the_current_page(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-021

    Seed enough rows for two pages at the default page size (50), narrow the
    ledger to that account, step to page 2, edit a row there and save. The
    ledger must stay on page 2 — old code reset the page on every save.
    """
    account_name = "Keep Place Tx E2E"
    category_name = "Keep Place Cat E2E"
    account_id = seed_account(account_name)
    category_id = seed_category(category_name)

    # 55 rows → 2 pages at page_size 50. One per day so the order is stable and
    # the oldest five land alone on page 2.
    today = datetime.date.today()
    for i in range(55):
        seed_transaction(
            account_id,
            category_id,
            12.34,
            date=today - datetime.timedelta(days=i),
            description=f"KeepPlace {i:02d}",
        )

    page.goto(f"{base_url}/transactions")
    filter_ledger_by_account(page, account_name)

    foot = page.locator(".k-ledger-foot")
    expect(foot).to_contain_text("Page 1 /", timeout=10000)

    # Step to page 2 via the forward chevron. The button is icon-only with no
    # accessible name, so match the Material icon ligature in its text.
    foot.locator("button").filter(has_text="chevron_right").click()
    expect(foot).to_contain_text("Page 2 /", timeout=10000)

    # Edit the first row on page 2, stamping a marker so we can prove the save
    # landed and that the marked row is the one still in view.
    row = page.locator(".q-table tbody tr").first
    row.get_by_role("button", name="Edit").click()
    edit_dialog = page.get_by_role("dialog")
    expect(edit_dialog.get_by_text("Edit Transaction", exact=True)).to_be_visible(timeout=5000)
    desc_field = edit_dialog.get_by_label("Description (optional)")
    desc_field.click(click_count=3)
    desc_field.fill("KeepPlace EDITED")
    edit_dialog.get_by_role("button", name="Save", exact=True).click()

    # The whole point of #22: the save does not yank us back to page 1.
    expect(foot).to_contain_text("Page 2 /", timeout=10000)
    expect(page.get_by_text("KeepPlace EDITED").first).to_be_visible(timeout=5000)
