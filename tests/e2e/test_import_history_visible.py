# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test: import history is reachable, not buried in nested panels.

Covers: KAL-CSV-033
Page URL: /import
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

STEP_FORMAT = 1


def test_file_history_is_expanded_by_default(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-033

    The import page lands on the Upload step; file history lives on the Format
    step. It used to sit collapsed inside an also-collapsed reference panel —
    two clicks deep on a step the user never lands on — so nobody found it.
    Both expanders now open by default: walking back to Format shows the
    history with no further clicks.
    """
    page.goto(f"{base_url}/import")

    page.locator(f'[data-step="{STEP_FORMAT}"]').click()
    panel = page.locator(f'[data-step-panel="{STEP_FORMAT}"]')
    expect(panel).to_be_visible(timeout=5000)

    # The File history expander is the inner one (DOM order: outer reference
    # panel first, nested File history last). It must be both visible — which
    # needs the outer panel open — and itself expanded, independent of whether
    # any imports have been recorded (the e2e app's shared state varies).
    history = panel.locator(".q-expansion-item", has_text="File history").last
    expect(history).to_be_visible(timeout=5000)
    expect(history).to_have_class(re.compile(r"q-expansion-item--expanded"))
