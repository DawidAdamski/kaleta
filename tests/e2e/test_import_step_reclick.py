# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E regression test: re-clicking the current step must not wedge the next.

Covers: KAL-CSV-036
Page URL: /import
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

STEP_FORMAT = 1
STEP_UPLOAD = 2


def test_reclicking_current_step_does_not_wedge_next_navigation(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-036

    The progress line lets you click the step already on screen. That used to
    re-run the whole repaint for a step that did not move, and a click landing
    mid-rebuild was dropped — so clicking the current step and then the next
    one left the reader stuck. Re-picking the current step now records the
    choice without a repaint, so the next click lands.
    """
    page.goto(f"{base_url}/import")
    expect(page.locator(f'[data-step-panel="{STEP_FORMAT}"]')).to_be_visible(timeout=5000)

    # Re-click the step already on screen, then move to the next one.
    page.locator(f'[data-step="{STEP_FORMAT}"]').click()
    page.locator(f'[data-step="{STEP_UPLOAD}"]').click()

    expect(page.locator(f'[data-step-panel="{STEP_UPLOAD}"]')).to_be_visible(timeout=5000)
    expect(page.locator(f'[data-step-panel="{STEP_FORMAT}"]')).to_be_hidden()
