# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for the phone dashboard and its tab bar (artboard 1f).

Covers: KAL-NAV-006, KAL-DSH-007

Both tests seed nothing. The suite shares one database and one user storage,
so a test that adds rows changes what every later file sees — and neither
claim here is about figures: one is about the navigation a narrow viewport
gets, the other about the shape the widgets are arranged in. Both hold on an
empty ledger and on a full one.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

PHONE = {"width": 390, "height": 844}

#: The five tabs, in order, as (data-tab value, visible label).
TABS: list[tuple[str, str]] = [
    ("nav.tab_home", "Home"),
    ("nav.tab_transactions", "Ledger"),
    ("nav.tab_add", "Add"),
    ("nav.tab_plan", "Plan"),
    ("nav.tab_more", "More"),
]

#: The minimum hit target the handoff asks for, in CSS pixels.
MIN_TAP_TARGET = 44


def _open_phone_dashboard(page: Page, base_url: str) -> None:
    page.set_viewport_size(PHONE)
    page.goto(f"{base_url}/")
    # The dashboard asks the browser how wide it is before choosing a layout,
    # so the bands only exist once the socket is up.
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)
    page.wait_for_selector("[data-band]", timeout=20000)


def test_a_narrow_viewport_gets_a_bottom_tab_bar(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-006"""
    _open_phone_dashboard(page, base_url)

    bar = page.locator(".k-tabbar")
    expect(bar).to_be_visible(timeout=10000)
    for data_tab, label in TABS:
        tab = bar.locator(f'[data-tab="{data_tab}"]')
        expect(tab).to_be_visible()
        box = tab.bounding_box()
        assert box is not None
        assert box["height"] >= MIN_TAP_TARGET, f"{label} is {box['height']}px tall"
        assert box["width"] >= MIN_TAP_TARGET, f"{label} is {box['width']}px wide"

    # The centre circle is the one target that is not a full-width column.
    add = bar.locator(".k-tabbar-add").bounding_box()
    assert add is not None
    assert min(add["width"], add["height"]) >= MIN_TAP_TARGET, add

    # Only "Add" is an icon alone; the other four are labelled.
    for _data_tab, label in TABS:
        if label == "Add":
            continue
        expect(bar.get_by_text(label, exact=True)).to_be_visible()

    # The bar sits at the foot of the viewport, not in the scroll.
    box = bar.bounding_box()
    assert box is not None
    assert round(box["y"] + box["height"]) == PHONE["height"]


def test_the_phone_header_has_one_way_into_the_palette(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-006

    The "Jump to…" pill is a sibling of the top-bar row, not a child of it,
    so hiding the row is not enough to hide the pill — left alone, a 390px
    header carried both it and the search icon, opening the same dialog.
    """
    _open_phone_dashboard(page, base_url)

    expect(page.locator(".k-phone-search")).to_be_visible(timeout=10000)
    expect(page.locator(".k-topnav-search")).to_be_hidden()
    expect(page.locator(".k-topnav")).to_be_hidden()


def test_the_drawer_waits_behind_more(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-006

    The drawer used to be opened unconditionally, which on a phone is an
    overlay covering the page you just asked for.
    """
    _open_phone_dashboard(page, base_url)

    drawer = page.locator("aside.q-drawer")
    expect(drawer).to_be_hidden(timeout=10000)

    page.locator('.k-tabbar [data-tab="nav.tab_more"]').click()

    expect(drawer).to_be_visible(timeout=10000)


def test_add_opens_the_new_transaction_form(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-006"""
    _open_phone_dashboard(page, base_url)

    page.locator('.k-tabbar [data-tab="nav.tab_add"]').click()

    page.wait_for_url(f"{base_url}/transactions?new=1", timeout=10000)
    expect(page.get_by_role("dialog")).to_be_visible(timeout=10000)


def _reset_widgets(page: Page) -> None:
    """Put the shared user storage back to the default widget set.

    The suite shares one NiceGUI user storage, so the stored layout this test
    reads is whatever the files before it left behind. Resetting first makes
    the claims below claims about the defaults rather than about test order,
    and leaves the storage cleaner than it found it.
    """
    page.get_by_role("button", name="Customize").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Customize Dashboard", exact=True)).to_be_visible(timeout=5000)
    dialog.get_by_role("button", name="Reset widgets").click()
    expect(dialog).to_be_hidden(timeout=10000)


def test_no_width_is_stranded_between_the_two_layouts(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-006

    Quasar hands the drawer over to overlay mode at 1023px by default, while
    the tab bar appears below 768px. Left alone, a window between the two got
    neither: a shut drawer and no tab bar. Since artboard `1e` the drawer is
    an overlay at every width and the top bar is the wide navigation, so the
    one line that must not have a gap in it is 768px: below it the tab bar,
    above it the top bar, and never a window with neither.
    """
    page.set_viewport_size({"width": 900, "height": 900})
    page.goto(f"{base_url}/transactions")
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)

    expect(page.locator(".k-topnav")).to_be_visible(timeout=10000)
    expect(page.locator(".k-tabbar")).to_be_hidden()


def test_the_phone_dashboard_stacks_into_bands(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-007"""
    _open_phone_dashboard(page, base_url)
    _reset_widgets(page)
    _open_phone_dashboard(page, base_url)

    for band, heading in (
        ("now", "Now"),
        ("month", "This month"),
        ("watch", "Watch"),
        ("latest", "Latest"),
    ):
        section = page.locator(f'[data-band="{band}"]')
        expect(section).to_be_visible(timeout=10000)
        expect(section.get_by_text(heading, exact=True).first).to_be_visible()

    now = page.locator('[data-band="now"]')
    expect(now.locator("[data-widget-id]").first).to_have_attribute(
        "data-widget-id", "safe_to_spend", timeout=10000
    )
    expect(now.get_by_text("Safe to spend", exact=True).first).to_be_visible()

    watch = page.locator('[data-band="watch"]')
    for label in (
        "Net Worth",
        "Savings rate, 6-mo avg",
        "Balance in 30 days",
        "Safety fund cover",
    ):
        expect(watch.get_by_text(label, exact=True).first).to_be_visible()
    # Plain type on the ground: a card here would repeat what the figure above
    # it already says, and the year-to-date net would appear twice.
    expect(watch.locator("[data-widget-id]")).to_have_count(0)

    # No grid, and nothing offering to drag cards around one. Customize
    # stays — which widgets you want is not a question about width.
    expect(page.locator("#dash-grid")).to_have_count(0)
    expect(page.locator("#dash-edit-btn-label")).to_have_count(0)
    expect(page.get_by_role("button", name="Customize")).to_be_visible()

    # The hero is a default widget since artboard `1e`, so a reset profile has
    # it ticked — and unticking it is the user's to do, at either width.
    page.get_by_role("button", name="Customize").click()
    dialog = page.get_by_role("dialog")
    hero_row = dialog.locator('[data-customize-row="safe_to_spend"]')
    expect(hero_row).to_be_visible(timeout=5000)
    expect(hero_row.locator('[role="checkbox"]')).to_have_attribute(
        "aria-checked", "true", timeout=5000
    )

    widths = page.evaluate("() => [document.scrollingElement.scrollWidth, window.innerWidth]")
    assert widths[0] <= widths[1], f"page scrolls sideways: {widths[0]} > {widths[1]}"


def test_a_wide_window_does_not_get_the_phone_layout(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-007

    The phone layout is chosen once, server-side, from the viewport width —
    so the guard that a wide window still gets the grid belongs next to the
    test that a narrow one does not. Both widths read in bands since artboard
    `1e`; what separates them is the grid and the tab bar. What the wide
    window does with its bands is KAL-DSH-008, in
    ``test_dashboard_desktop.py``.
    """
    page.set_viewport_size({"width": 1360, "height": 900})
    page.goto(f"{base_url}/")
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)

    expect(page.locator("#dash-grid")).to_be_visible(timeout=20000)
    expect(page.locator(".k-tabbar")).to_be_hidden()
