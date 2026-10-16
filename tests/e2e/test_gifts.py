# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Gift Planning.

Page URL: /wizard/gifts
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import clear_gifts


def _add_gift(page: Page, person: str, occasion: str, amount: str) -> None:
    page.get_by_role("button", name="Add gift").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_label("Who it's for", exact=True).fill(person)
    dialog.get_by_label("Occasion", exact=True).fill(occasion)
    amount_field = dialog.get_by_role("spinbutton", name="Amount", exact=True)
    amount_field.click(click_count=3)
    amount_field.fill(amount)
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).not_to_be_visible(timeout=5000)


def test_maintain_the_gift_list(page: Page, base_url: str) -> None:
    """Covers: KAL-GFT-001

    Adding "Mum — birthday — 200.00" and "Mum — Christmas — 150.00" shows both
    grouped under "Mum" and a yearly gifts total of 350.00. The gift total is
    sum-based across the whole family, so the test clears gifts first and in a
    finally (rerun-safe, and the shared-DB #19 lesson).
    """
    clear_gifts()
    try:
        page.goto(f"{base_url}/wizard/gifts")
        expect(page.get_by_text("Gifts", exact=True).first).to_be_visible(timeout=5000)

        _add_gift(page, "Mum", "birthday", "200")
        _add_gift(page, "Mum", "Christmas", "150")

        # Both entries appear, grouped under one "Mum" card.
        mum_card = page.locator(".q-card").filter(has_text="Mum")
        expect(mum_card).to_have_count(1, timeout=5000)
        expect(mum_card.get_by_text("birthday", exact=True)).to_be_visible()
        expect(mum_card.get_by_text("Christmas", exact=True)).to_be_visible()
        # The person subtotal.
        expect(mum_card.get_by_text("350.00", exact=True)).to_be_visible()

        # The yearly total in the header reads 350.00.
        total_label = page.get_by_text("Yearly gifts total", exact=True)
        expect(total_label).to_be_visible()
        total_value = total_label.locator("xpath=following-sibling::*[1]")
        expect(total_value).to_have_text("350.00")
    finally:
        clear_gifts()
