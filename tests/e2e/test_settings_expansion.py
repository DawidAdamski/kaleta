# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Settings PR2 expansion (ux-sidebar-workflow-and-settings).

Covers: KAL-SET-024, KAL-SET-025, KAL-SET-026
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_settings_privacy_tab_is_available(page: Page) -> None:
    """Covers: KAL-SET-024 — Privacy & diagnostics tab exposes event capture controls."""
    page.goto("/settings")
    page.get_by_role("tab", name="Privacy & diagnostics").click()
    expect(page.get_by_text("Capture anonymous error events")).to_be_visible()
    expect(page.get_by_role("button", name="Copy session ID")).to_be_visible()


def test_settings_features_transfer_pairing_controls(page: Page) -> None:
    """Covers: KAL-SET-025 — Features tab exposes transfer pairing thresholds."""
    page.goto("/settings")
    page.get_by_role("tab", name="Features").click()
    expect(page.get_by_text("Transfer pairing")).to_be_visible()
    expect(page.get_by_text("Max days apart")).to_be_visible()


def test_settings_features_upcoming_planned_window(page: Page) -> None:
    """Covers: KAL-SET-026 — Features tab exposes the upcoming-planned window."""
    page.goto("/settings")
    page.get_by_role("tab", name="Features").click()

    card = page.locator(".q-card").filter(has_text="Upcoming planned transactions")
    expect(card).to_be_visible(timeout=10000)
    for option in ("Off", "7 days", "30 days"):
        expect(card.get_by_role("button", name=option, exact=True)).to_be_visible()

    # Quasar marks the option in force with aria-pressed; every button in the
    # group carries the same classes, so the class list proves nothing here.
    expect(card.get_by_role("button", name="7 days", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(card.get_by_role("button", name="Off", exact=True)).to_have_attribute(
        "aria-pressed", "false"
    )

    # The pick has to survive a reload, or the ledger reads a window the user
    # did not choose the next time they open it.
    card.get_by_role("button", name="30 days", exact=True).click()
    expect(page.get_by_text("Settings saved").first).to_be_visible(timeout=5000)
    try:
        page.goto("/settings")
        page.get_by_role("tab", name="Features").click()
        card = page.locator(".q-card").filter(has_text="Upcoming planned transactions")
        expect(card.get_by_role("button", name="30 days", exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
    finally:
        card.get_by_role("button", name="7 days", exact=True).click()
        expect(page.get_by_text("Settings saved").first).to_be_visible(timeout=5000)
