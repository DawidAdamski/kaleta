# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test for the Accounts "group by" control showing its active option.

Covers: KAL-ACC-011
Page URL: /accounts
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account


def _channel_sum(css_colour: str) -> int:
    """Sum the R, G, B channels of a computed `rgb(...)`/`rgba(...)` string."""
    inside = css_colour[css_colour.index("(") + 1 : css_colour.index(")")]
    parts = [p.strip() for p in inside.split(",")[:3]]
    return sum(int(float(p)) for p in parts)


def test_active_group_by_option_is_ink_filled(page: Page, base_url: str) -> None:
    """Covers: KAL-ACC-011

    The group-by toggle defaults to "Type". The chosen option must be filled
    with ink (``--k-ink`` ≈ #1C1A15) so it reads as selected at a glance —
    not with the accent (``--q-primary`` ≈ #B4591F) a plain toggle used, which
    the user could not tell apart from the unpicked option.
    """
    seed_account("Group-by E2E Account")

    page.goto(f"{base_url}/accounts")
    expect(page.get_by_text("Accounts", exact=True).first).to_be_visible(timeout=5000)

    toggle = page.locator(".q-btn-toggle").first
    expect(toggle).to_be_visible(timeout=5000)

    # Quasar marks the chosen toggle button with `bg-primary`; k-segment then
    # repaints that fill as ink.
    selected = toggle.locator("button.bg-primary")
    expect(selected).to_have_count(1)
    bg = selected.evaluate("el => getComputedStyle(el).backgroundColor")

    # Ink (#1C1A15) sums to ~75; the old accent fill (#B4591F) sums to ~300.
    assert _channel_sum(bg) < 150, f"active option not ink-filled: {bg}"
