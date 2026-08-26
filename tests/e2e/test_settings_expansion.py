# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Settings PR2 expansion (ux-sidebar-workflow-and-settings).

Covers: KAL-SET-024, KAL-SET-025
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
