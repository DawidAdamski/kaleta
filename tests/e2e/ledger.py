# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers for driving the transactions ledger from e2e tests.

The filters became chips (artboard 2a): each control now lives in a menu that
opens from its chip and overlays the table, so a test that wants to type into
one has to open it first and close it before touching the rows underneath.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def search_ledger(page: Page, text: str) -> None:
    """Filter the ledger by description through the search chip."""
    chip = page.locator(".k-chip-search")
    expect(chip).to_be_visible(timeout=10000)
    chip.click()
    search = page.get_by_label("Search description")
    expect(search).to_be_visible(timeout=5000)
    search.click(click_count=3)
    search.fill(text)
    page.keyboard.press("Escape")
