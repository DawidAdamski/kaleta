# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test: buttons give a press affordance while held.

Covers: KAL-UIX-001
Page URL: /import (any enabled button; the Continue control is a stable one)
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

# translateY(1px) computes to this transform matrix; "none" is the resting state.
_PRESSED = "matrix(1, 0, 0, 1, 0, 1)"
_RESTING = "none"


def test_button_dips_while_held_and_springs_back(page: Page, base_url: str) -> None:
    """Covers: KAL-UIX-001

    A global `.q-btn:active` rule nudges any enabled button down a pixel while
    it is held, so a click is felt even where Quasar's ripple is faint. It is a
    composited transform, so no layout shifts, and a disabled button stays put.
    """
    page.goto(f"{base_url}/import")

    # The import page opens on Format; its Continue control is enabled there.
    button = page.locator("[data-continue]")
    expect(button).to_be_visible(timeout=5000)
    expect(button).to_have_css("transform", _RESTING)

    button.hover()
    page.mouse.down()
    try:
        expect(button).to_have_css("transform", _PRESSED)
    finally:
        page.mouse.up()

    expect(button).to_have_css("transform", _RESTING)
