# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test: typing in the ledger search leaves one table, not two.

Covers: KAL-TXN-020
Page URL: /transactions
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_category, seed_transaction

TOKEN = "QZXSEARCHTOKEN"


def _eyebrow_count(page: Page) -> int:
    text = page.locator("[data-page-eyebrow]").inner_text()
    match = re.search(r"\d[\d  ]*", text)
    assert match, text
    return int(match.group(0).replace(" ", "").replace(" ", ""))


def test_typing_in_search_leaves_a_single_table(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-020

    The search box used to fire one async table refresh per keystroke, and
    because the render awaits the database, two could be in flight at once —
    the slower one painted a second table under the faster one, with the
    eyebrow count disagreeing with the rows below it. Typing a word now leaves
    exactly one table whose count matches its own footer.
    """
    account = seed_account("Search Race Account")
    category = seed_category("Search Race Category")
    for i in range(3):
        seed_transaction(account, category, 10 + i, description=f"{TOKEN} row {i}")

    page.goto(f"{base_url}/transactions")

    chip = page.locator(".k-chip-search")
    expect(chip).to_be_visible(timeout=10000)
    chip.click()
    search = page.get_by_label("Search description", exact=True)
    expect(search).to_be_visible(timeout=5000)

    # Type character by character with no delay — faster than a DB round-trip,
    # so the per-keystroke refreshes the old code fired genuinely overlap (one
    # table per letter without the fix). `fill` would emit once and never race.
    search.press_sequentially(TOKEN, delay=0)
    page.keyboard.press("Escape")
    expect(page.locator(".q-menu")).to_have_count(0, timeout=10000)

    ledger = page.locator(".k-ledger-card")
    # The symptom was a second table stacked under the first.
    expect(ledger.locator(".q-table")).to_have_count(1, timeout=10000)

    # The three seeded rows match, and the eyebrow agrees with the footer that
    # sits under the one table — not a stale count from a superseded render.
    expect(ledger.get_by_text(re.compile(r"Showing 1–3 of 3"))).to_be_visible(timeout=10000)
    assert _eyebrow_count(page) == 3
