# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test: the import settings step links to the saved import rules.

Covers: KAL-CSV-035
Page URL: /import
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect

IMPORT_CSV = Path(__file__).resolve().parents[2] / "test_import.csv"
STEP_SETTINGS = 4


def test_settings_step_links_to_saved_mappings(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-035

    Saved column mappings live in Settings -> Import, and the import flow had
    no way to reach them. A parsed file lands on the settings step, where a
    "Manage saved mappings" link — beside "Remember this mapping" — points to
    that list, opening in a new tab so the in-progress import survives.
    """
    page.goto(f"{base_url}/import")

    # A recognised CSV parses to ready, which puts the wizard on the settings
    # step; the hidden upload input still takes the file on the Format landing.
    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))

    panel = page.locator(f'[data-step-panel="{STEP_SETTINGS}"]')
    expect(panel).to_be_visible(timeout=10000)

    link = panel.get_by_role("link", name="Manage saved mappings")
    expect(link).to_be_visible()
    expect(link).to_have_attribute("href", "/settings?tab=import")
    expect(link).to_have_attribute("target", "_blank")
