# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for the desktop rethink — top bar, palette, bands (artboard 1e).

Covers: KAL-NAV-007, KAL-NAV-008, KAL-DSH-008

Seeds nothing. The suite shares one database and one user storage, and
none of these claims is about a figure: they are about which navigation a
wide viewport gets and which band each widget lands in. Both hold on an
empty ledger and on a full one.
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

DESKTOP = {"width": 1360, "height": 900}

#: The palette's own field, the one thing in the dialog that takes typing.
PALETTE_PLACEHOLDER = "Jump to a page…"

#: The five sections, in bar order, as (group key, visible label).
SECTIONS: list[tuple[str, str]] = [
    ("nav.group_capture", "Capture"),
    ("nav.group_monthly", "Month"),
    ("nav.group_plans", "Plans"),
    ("nav.group_insight", "Insight"),
    ("nav.group_setup", "Setup"),
]


def _open_desktop(page: Page, base_url: str, path: str = "/") -> None:
    page.set_viewport_size(DESKTOP)
    page.goto(f"{base_url}{path}")
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)


def test_a_wide_viewport_navigates_from_the_top_bar(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-007"""
    _open_desktop(page, base_url, "/transactions")

    bar = page.locator(".k-topnav")
    expect(bar).to_be_visible(timeout=10000)
    for key in ("nav.dashboard", "nav.wizard"):
        expect(bar.locator(f'[data-nav="{key}"]')).to_be_visible()
    for group_key, label in SECTIONS:
        section = bar.locator(f'[data-section="{group_key}"]')
        expect(section).to_be_visible()
        expect(section).to_contain_text(label)

    # The drawer is the phone's long tail now; a desktop has no way to open it
    # and no gutter reserved for it.
    expect(page.locator("aside.q-drawer")).to_be_hidden()

    # /transactions lives in Capture, so Capture is the section you are in.
    expect(bar.locator('[data-section="nav.group_capture"]')).to_have_attribute(
        "aria-current", "page"
    )
    expect(bar.locator('[data-section="nav.group_setup"]')).not_to_have_attribute(
        "aria-current", "page"
    )


def test_a_section_menu_routes(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-007"""
    _open_desktop(page, base_url)

    page.locator('.k-topnav [data-section="nav.group_insight"]').click()
    entry = page.locator('[data-nav="nav.net_worth"]')
    expect(entry).to_be_visible(timeout=10000)
    entry.click()

    expect(page).to_have_url(f"{base_url}/net-worth", timeout=10000)


def _open_palette(page: Page) -> Locator:
    """⌘K, then wait for the field to have the caret before typing into it.

    Quasar hands ``data-autofocus`` its focus when the dialog's transition
    ends, not when the dialog mounts — type before that and the keystrokes
    land on ``<body>`` and are gone.
    """
    page.keyboard.press("Control+k")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=10000)
    expect(dialog.get_by_placeholder(PALETTE_PLACEHOLDER)).to_be_focused(timeout=5000)
    return dialog


def test_the_palette_reaches_a_page_by_name(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-008"""
    _open_desktop(page, base_url)

    dialog = _open_palette(page)

    rows = dialog.locator("[data-palette-row]")
    expect(rows.first).to_be_visible()
    page.keyboard.type("institu")
    expect(dialog.locator('[data-palette-row="nav.institutions"]')).to_be_visible(timeout=5000)
    expect(dialog.locator('[data-palette-row="nav.transactions"]')).to_be_hidden()

    page.keyboard.press("Enter")

    expect(page).to_have_url(f"{base_url}/institutions", timeout=10000)


def test_the_palette_says_when_nothing_matches(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-008

    An empty list and a list of everything look the same from across the
    room; only one of them is honest about having found nothing.
    """
    _open_desktop(page, base_url)

    dialog = _open_palette(page)
    page.keyboard.type("zzzznothing")

    expect(dialog.get_by_text("No page by that name.")).to_be_visible(timeout=5000)
    expect(dialog.locator("[data-palette-row]:visible")).to_have_count(0)


def test_the_desktop_dashboard_reads_in_bands(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-008"""
    _open_desktop(page, base_url)
    page.wait_for_selector("#dash-bands", timeout=20000)

    bands = page.locator("#dash-bands [data-band]")
    expect(bands).to_have_count(4)
    for index, band in enumerate(("now", "month", "watch", "latest")):
        expect(bands.nth(index)).to_have_attribute("data-band", band)

    now = page.locator('[data-band="now"]')
    expect(now.locator("[data-widget-id]").first).to_have_attribute(
        "data-widget-id", "safe_to_spend", timeout=10000
    )

    # Editing belongs to the band whose cards it moves.
    month = page.locator('[data-band="month"]')
    expect(month.locator("#dash-edit-btn-label")).to_be_visible()


def test_only_the_month_band_is_inside_the_grid(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-008

    ``#dash-grid`` *is* the drag scope — SortableJS, the resize button and
    the layout endpoint all key off that id — so "drag-and-drop is scoped to
    the Month band" is the claim that nothing else is inside it.
    """
    _open_desktop(page, base_url)
    page.wait_for_selector("#dash-grid", timeout=20000)

    in_grid = page.evaluate(
        """() => [...document.querySelectorAll('#dash-grid [data-widget-id]')]
                  .map(e => e.dataset.widgetId)"""
    )
    in_month = page.evaluate(
        """() => [...document.querySelectorAll('[data-band="month"] [data-widget-id]')]
                  .map(e => e.dataset.widgetId)"""
    )
    assert in_grid == in_month, (in_grid, in_month)
    assert "safe_to_spend" not in in_grid
    assert "recent_transactions" not in in_grid

    # Every widget still reaches the layout endpoint, or a drag inside Month
    # would save a layout that had lost the hero and the Latest list.
    posted = page.evaluate(
        """() => [...document.querySelectorAll('#dash-bands [data-widget-id]')]
                  .map(e => e.dataset.widgetId)"""
    )
    assert "safe_to_spend" in posted
    assert set(in_grid) <= set(posted)
