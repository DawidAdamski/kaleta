# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Gift Planning.

Page URL: /wizard/gifts
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    clear_gifts,
    delete_reserve_fund,
    delete_transaction,
    primary_irregular_fund_id,
    seed_account,
    seed_category,
    seed_gift,
    seed_reserve_fund,
    seed_transaction,
)


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


def test_gift_total_feeds_the_irregular_fund(page: Page, base_url: str) -> None:
    """Covers: KAL-GFT-002

    The yearly gifts total (200.00 + 150.00 = 350.00) shows on the irregular
    fund page as a read-only "Gifts" line. The line rides on the primary
    (oldest live) irregular fund, so the test opens exactly that fund. The gift
    total is sum-based across the family, so gifts are cleared before and in a
    finally; the seeded fund is removed too (shared-DB / rerun-safe, #19).
    """
    clear_gifts()
    account_id = seed_account("Konto funduszu nieregularnego (e2e)")
    fund_id = seed_reserve_fund(
        "Wydatki nieregularne (e2e)", 0.0, account_id, kind="irregular", emergency_multiplier=None
    )
    try:
        seed_gift("Mum", "birthday", 200)
        seed_gift("Mum", "Christmas", 150)
        primary_id = primary_irregular_fund_id()
        assert primary_id is not None

        page.goto(f"{base_url}/wizard/safety-funds/{primary_id}")
        gifts_row = page.get_by_test_id("irregular-derived-gifts")
        expect(gifts_row).to_be_visible(timeout=5000)
        # A "Gifts" line with the yearly total 350.00 is included.
        expect(gifts_row.get_by_text("Gifts", exact=True)).to_be_visible()
        expect(gifts_row.get_by_text("350.00", exact=True)).to_be_visible()
    finally:
        clear_gifts()
        delete_reserve_fund(fund_id)


def test_mark_a_gift_as_bought(page: Page, base_url: str) -> None:
    """Covers: KAL-GFT-003

    A gift planned at 200.00, linked to a 189.99 expense in the ledger, is
    marked bought and shows that actual cost. Gifts are sum-based across the
    family, so gifts are cleared before and in a finally; the seeded expense is
    removed too (shared-ledger / rerun-safe, #19).
    """
    clear_gifts()
    account_id = seed_account("Konto (e2e gift bought)")
    category_id = seed_category("Prezenty e2e bought", "expense")
    tx_id = seed_transaction(account_id, category_id, 189.99, description="Prezent dla mamy e2e")
    gift_id = seed_gift("Mum", "birthday", 200)
    try:
        page.goto(f"{base_url}/wizard/gifts")
        row = page.get_by_test_id(f"gift-row-{gift_id}")
        expect(row).to_be_visible(timeout=5000)

        row.get_by_role("button", name="Mark as bought").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible(timeout=5000)
        # Pick the 189.99 expense from the transaction select.
        dialog.get_by_label("Transaction", exact=True).click()
        page.get_by_role("option").filter(has_text="189.99").first.click()
        dialog.get_by_role("button", name="Link").click()
        expect(dialog).not_to_be_visible(timeout=5000)

        # The gift is marked bought with its actual cost.
        bought_row = page.get_by_test_id(f"gift-row-{gift_id}")
        expect(bought_row.get_by_test_id("gift-bought-badge")).to_be_visible(timeout=5000)
        expect(bought_row.get_by_test_id("gift-actual-cost")).to_have_text("189.99")
    finally:
        clear_gifts()
        delete_transaction(tx_id)
