# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for the weekly-grouping knob and the About tab's debug panel.

Covers: KAL-SET-027, KAL-SET-028
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

ISO_OPTION = "Monday to Sunday (ISO)"
MONTH_OPTION = "In sevens from the 1st"


def _weekly_grouping_card(page: Page):
    return page.locator(".q-card").filter(has_text="Weekly grouping")


def _pick_weekly_grouping(page: Page, option: str) -> None:
    """Choose an option and wait out the reload the knob triggers."""
    card = _weekly_grouping_card(page)
    card.locator(".q-select").click()
    page.locator(".q-menu").last.get_by_text(option, exact=True).click()
    # The knob reloads the page so every weekly subtotal is drawn again.
    page.wait_for_load_state("networkidle")


def _open_general_tab(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="General").click()
    expect(_weekly_grouping_card(page)).to_be_visible(timeout=10000)


def test_weekly_grouping_knob_offers_both_modes_and_persists(page: Page, base_url: str) -> None:
    """Covers: KAL-SET-027 — Weekly grouping is a General knob that survives a reload."""
    _open_general_tab(page, base_url)
    card = _weekly_grouping_card(page)

    # ISO is what a fresh session buckets by; the select shows the option in force.
    expect(card.locator(".q-select")).to_contain_text(ISO_OPTION)

    card.locator(".q-select").click()
    menu = page.locator(".q-menu").last
    expect(menu.get_by_text(ISO_OPTION, exact=True)).to_be_visible()
    expect(menu.get_by_text(MONTH_OPTION, exact=True)).to_be_visible()
    menu.get_by_text(MONTH_OPTION, exact=True).click()
    page.wait_for_load_state("networkidle")

    try:
        _open_general_tab(page, base_url)
        expect(_weekly_grouping_card(page).locator(".q-select")).to_contain_text(MONTH_OPTION)
    finally:
        # Left as found: every other e2e test reads the ledger's default weeks.
        _open_general_tab(page, base_url)
        _pick_weekly_grouping(page, ISO_OPTION)


def test_debug_panel_is_visible_under_debug_and_masks_the_secret(page: Page, base_url: str) -> None:
    """Covers: KAL-SET-028 — the debug panel is behind KALETA_DEBUG.

    The e2e instance runs with ``KALETA_DEBUG=true`` (see tests/e2e/conftest.py),
    which is the condition the panel is gated on.
    """
    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="About").click()

    card = page.locator(".q-card").filter(has_text="Debug info")
    expect(card).to_be_visible(timeout=10000)
    expect(card.get_by_role("button", name="Copy debug info")).to_be_visible()

    card.get_by_text("Show details", exact=True).click()
    expect(card.get_by_text("Versions", exact=True)).to_be_visible(timeout=5000)
    expect(card.get_by_text("Settings in force", exact=True)).to_be_visible()

    # The panel names the secret key and shows *** instead of its value.
    secret_row = card.locator(".row").filter(has_text="secret_key").first
    expect(secret_row).to_contain_text("***")
