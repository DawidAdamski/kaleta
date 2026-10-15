# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E for Feature: Dashboard — long account names stay inside their tiles.

Covers: KAL-DSH-010

The balance card names its largest accounts as quiet tiles under the hero
figure. When several long names share the row each tile is narrow, and a name
must be clipped to its tile (ellipsis) rather than render at its full width and
spill past the tile and the card's edge — the overflow reported in dogfooding
(#19).

Seeds three accounts with deliberately long, synthetic names and balances large
enough to rank them as the three named tiles, then asserts no tile's name
reaches past the card.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import delete_account, seed_account, update_account

DESKTOP = {"width": 1360, "height": 900}

#: Synthetic, intentionally long — never real account names (privacy).
LONG_NAMES = (
    "eKonto oszczędnościowe — fundusz awaryjny gospodarstwa domowego 2026",
    "eKonto oszczędnościowe — wakacje i urlop rodzinny długoterminowy plan",
    "mBiznes konto standardowe firmowe rozliczeniowe operacyjne bieżące",
)


def test_long_account_names_stay_within_the_card(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-010"""
    # These balances dominate the shared instance's figures on purpose (so the
    # accounts are the three named tiles), so the accounts are removed in the
    # `finally` — otherwise they would skew the global totals and tile layout
    # the other dashboard/transactions e2e tests on this worker assert on.
    account_ids = [seed_account(name) for name in LONG_NAMES]
    try:
        for account_id in account_ids:
            update_account(account_id, balance="99999999.00")

        page.set_viewport_size(DESKTOP)
        page.goto(f"{base_url}/")
        page.wait_for_function("() => window.did_handshake === true", timeout=20000)

        card = page.locator('[data-widget-id="balance_card"]')
        expect(card).to_be_visible(timeout=10000)
        chips = card.locator(".k-account-chip")
        expect(chips.first).to_be_visible(timeout=10000)

        card_box = card.bounding_box()
        assert card_box is not None
        card_right = card_box["x"] + card_box["width"]

        # Every account tile's name label must stay within the card. On the
        # broken layout the nowrap name rendered at its intrinsic width and ran
        # well past the card's right edge; truncation keeps it in its own tile.
        count = chips.count()
        assert count >= 1
        for i in range(count):
            label = chips.nth(i).locator(".k-card-caption")
            box = label.bounding_box()
            assert box is not None
            label_right = box["x"] + box["width"]
            assert label_right <= card_right + 1, (
                f"account tile #{i} name overflows the card: "
                f"label right={label_right:.1f} > card right={card_right:.1f}"
            )

        # The name is clipped with an ellipsis (not hard-cut), and the full name
        # stays reachable as a tooltip — the other half of KAL-DSH-010.
        first_name = chips.first.locator(".k-card-caption")
        full_name = first_name.inner_text()
        assert first_name.evaluate("el => getComputedStyle(el).textOverflow") == "ellipsis"
        first_name.hover()
        tooltip = page.locator(".q-tooltip")
        expect(tooltip).to_be_visible(timeout=5000)
        assert full_name.strip() and full_name.strip() in tooltip.inner_text()
    finally:
        for account_id in account_ids:
            delete_account(account_id)
