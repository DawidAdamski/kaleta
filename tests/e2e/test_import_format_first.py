# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test: the import page opens on Format and the format chip selects.

Covers: KAL-CSV-034
Page URL: /import
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

STEP_FORMAT = 1
STEP_UPLOAD = 2


def test_import_opens_on_format_and_chip_selects(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-034

    The page used to land on Upload — a step past the which-bank question —
    and the format chips did nothing until a file existed. Now it opens on
    Format and choosing a format (the page's default) lights the chip at once,
    before any upload.
    """
    page.goto(f"{base_url}/import")

    # Lands on Format, not Upload.
    expect(page.locator(f'[data-step-panel="{STEP_FORMAT}"]')).to_be_visible(timeout=5000)
    expect(page.locator(f'[data-step-panel="{STEP_UPLOAD}"]')).to_be_hidden()

    # Choosing a format with no file still selects it — the chip lights up.
    chip = page.locator(f'[data-step-panel="{STEP_FORMAT}"] .k-format-chip').filter(
        has_text="mBank"
    )
    expect(chip).to_be_visible()
    expect(chip).not_to_have_class(re.compile(r"k-format-chip--on"))
    chip.click()
    expect(chip).to_have_class(re.compile(r"k-format-chip--on"))
