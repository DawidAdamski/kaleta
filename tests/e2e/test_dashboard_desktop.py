# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for the wide viewport — docked drawer, palette, widget grid.

Covers: KAL-NAV-007, KAL-NAV-008, KAL-NAV-009, KAL-DSH-008, KAL-DSH-009

Seeds nothing. The suite shares one database and one user storage, and
none of these claims is about a figure: they are about which navigation a
wide viewport gets and what shape the widgets are arranged in. Both hold
on an empty ledger and on a full one.
"""

from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

DESKTOP = {"width": 1360, "height": 900}

#: The palette's own field, the one thing in the dialog that takes typing.
PALETTE_PLACEHOLDER = "Jump to a page…"

#: Artboard `1c`'s drawer, and artboard `2a`'s rail.
DRAWER_WIDTH = 236
MINI_WIDTH = 64


def _open_desktop(page: Page, base_url: str, path: str = "/") -> None:
    page.set_viewport_size(DESKTOP)
    page.goto(f"{base_url}{path}")
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)


def _drawer(page: Page) -> Locator:
    return page.locator("aside.q-drawer")


def _wait_for_drawer_width(page: Page, width: int) -> None:
    """Block until the drawer has finished animating to *width*.

    Quasar puts ``q-drawer--mini`` on the aside when the state flips and then
    animates the width over it, so a ``bounding_box()`` read as soon as the
    class lands catches a frame of the 236-to-64 transition.
    """
    page.wait_for_function(
        """(want) => {
          const a = document.querySelector('aside.q-drawer');
          return a && Math.round(a.getBoundingClientRect().width) === want;
        }""",
        arg=width,
        timeout=10000,
    )


def _set_mini(page: Page, mini: bool) -> None:
    """Put the drawer in the asked-for state through the header's own toggle."""
    toggle = page.locator("[data-drawer-mini-toggle]")
    expect(toggle).to_be_visible(timeout=10000)
    is_mini = page.locator(".q-drawer--mini").count() > 0
    if is_mini != mini:
        toggle.click()
    _wait_for_drawer_width(page, MINI_WIDTH if mini else DRAWER_WIDTH)


def test_a_wide_viewport_gets_the_docked_drawer(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-007"""
    _open_desktop(page, base_url, "/transactions")
    _set_mini(page, False)

    drawer = _drawer(page)
    expect(drawer).to_be_visible(timeout=10000)
    box = drawer.bounding_box()
    assert box is not None
    assert round(box["width"]) == DRAWER_WIDTH, box

    # Docked, not an overlay: the page begins where the drawer ends, rather
    # than under it. `.q-page-container` spans the window and holds the gutter
    # as padding; `main.q-page` is the box that gets pushed across.
    page_left = page.evaluate(
        "() => Math.round(document.querySelector('main.q-page').getBoundingClientRect().left)"
    )
    assert page_left == DRAWER_WIDTH, page_left

    # /transactions lives in Capture, so its entry is the one that is marked.
    active = drawer.locator(".k-nav-item--active")
    expect(active).to_have_count(1)
    expect(active).to_contain_text("Transactions")

    # The header says where you are, after the wordmark and its hairline.
    header = page.locator(".k-header")
    expect(header.locator(".k-wordmark")).to_have_text("Kaleta")
    expect(header.locator(".k-header-divider")).to_be_visible()
    expect(header.locator(".k-header-page")).to_have_text("Transactions")
    assert page.title() == "Transactions · Kaleta", page.title()

    # The pill is the wide window's way into the palette; the phone's icon
    # and its tab bar are not beside it.
    expect(page.locator(".k-header-search")).to_be_visible()
    expect(page.locator(".k-phone-search")).to_be_hidden()
    expect(page.locator(".k-tabbar")).to_be_hidden()


def test_the_drawer_collapses_to_a_rail_and_stays_one(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-007

    ``sidebar_mini`` is one stored preference, not a per-page one: the
    artboards draw the drawer expanded on the dashboard and mini on every
    working screen, but what gets you from one to the other is this toggle,
    and it has to survive the next page load.
    """
    _open_desktop(page, base_url)
    _set_mini(page, False)

    page.locator("[data-drawer-mini-toggle]").click()
    expect(page.locator(".q-drawer--mini")).to_have_count(1, timeout=10000)
    _wait_for_drawer_width(page, MINI_WIDTH)
    # A rail of icons: the labels are gone, the icons are not.
    expect(_drawer(page).get_by_text("Payment Calendar", exact=True)).to_be_hidden()

    _open_desktop(page, base_url, "/transactions")
    expect(page.locator(".q-drawer--mini")).to_have_count(1, timeout=10000)
    _wait_for_drawer_width(page, MINI_WIDTH)

    # Leave the shared storage expanded for the files after this one.
    _set_mini(page, False)


def test_settings_offers_the_same_drawer_choice(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-007

    The header's chevron and Settings - Appearance write the same
    `sidebar_mini` key, so choosing "Collapsed" here has to reach the drawer
    on the next page. Asserting the toggle is on screen says nothing about
    that wiring: `set_user_key("sidebar_mini", ...)` is the whole claim.
    """
    _open_desktop(page, base_url, "/settings")
    page.get_by_role("tab", name="Appearance").click()

    expect(page.get_by_text("Sidebar", exact=True)).to_be_visible(timeout=10000)
    collapsed = page.get_by_role("button", name="Collapsed")
    expanded = page.get_by_role("button", name="Expanded")
    expect(collapsed).to_be_visible()
    expect(expanded).to_be_visible()

    collapsed.click()
    # The toggle saves and toasts; the drawer it is choosing for is the next
    # page's, so that is where the choice has to show up.
    expect(page.get_by_text("Settings saved.").first).to_be_visible(timeout=10000)
    _open_desktop(page, base_url)
    expect(page.locator(".q-drawer--mini")).to_have_count(1, timeout=10000)
    _wait_for_drawer_width(page, MINI_WIDTH)

    # …and back, so the files after this one find the drawer expanded.
    _open_desktop(page, base_url, "/settings")
    page.get_by_role("tab", name="Appearance").click()
    page.get_by_role("button", name="Expanded").click()
    expect(page.get_by_text("Settings saved.").first).to_be_visible(timeout=10000)
    _open_desktop(page, base_url)
    _wait_for_drawer_width(page, DRAWER_WIDTH)


def test_the_avatar_menu_carries_the_account_actions(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-009

    The artboards end the header with a 28px initials disc and nothing else,
    so the two buttons that used to sit beside it are inside the menu it
    drops. Losing them there would be losing the only way to log out.
    """
    _open_desktop(page, base_url)

    avatar = page.locator(".k-avatar")
    expect(avatar).to_be_visible(timeout=10000)
    # Two letters of the account name, which is what the disc is for.
    assert len(avatar.inner_text().strip()) == 2, avatar.inner_text()
    avatar.click()

    menu = page.locator(".q-menu")
    expect(menu).to_be_visible(timeout=10000)
    expect(menu.get_by_text("Log out", exact=True)).to_be_visible()
    expect(menu.get_by_text("Close database", exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    expect(menu).to_be_hidden(timeout=10000)


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


def test_the_palette_opens_from_inside_a_text_field(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-008

    A search box is exactly where "take me to another page" gets asked, and
    ``ui.keyboard`` ignores ``input`` by default — so the shortcut was inert
    in the one place it is most wanted. It is a document listener now, which
    also lets it call ``preventDefault`` before Chrome takes Ctrl+K for its
    own search box.
    """
    _open_desktop(page, base_url, "/credit-calculator")

    field = page.locator("input").first
    expect(field).to_be_visible(timeout=10000)
    field.click()
    expect(field).to_be_focused()

    page.keyboard.press("Control+k")

    expect(page.get_by_role("dialog")).to_be_visible(timeout=10000)


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


def test_enter_on_an_empty_palette_stays_put(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-008

    An empty needle is in every label, so the "first match" of nothing typed
    is whatever happens to be first — ⌘K and a stray Enter must not be a
    navigation.
    """
    _open_desktop(page, base_url, "/transactions")

    dialog = _open_palette(page)
    page.keyboard.press("Enter")

    expect(dialog).to_be_visible()
    expect(page).to_have_url(f"{base_url}/transactions")


def _wait_for_grid_settled(page: Page) -> None:
    """Block until NiceGUI has finished streaming widgets into ``#dash-grid``.

    Widgets arrive one at a time over the websocket, and the layout POST
    serialises *whatever is in the DOM right now* — fire it mid-stream and it
    persists a dashboard missing every widget yet to arrive. Wait for the
    count to hold steady rather than guessing at a sleep.
    """
    page.wait_for_function(
        """() => {
          const grid = document.getElementById('dash-grid');
          if (!grid) return false;
          const n = grid.querySelectorAll('[data-widget-id]').length;
          const s = window.__kaletaGridSettle || {count: -1, stable: 0};
          s.stable = n > 0 && n === s.count ? s.stable + 1 : 0;
          s.count = n;
          window.__kaletaGridSettle = s;
          return s.stable >= 3;
        }""",
        polling=200,
        timeout=30000,
    )


def test_the_desktop_dashboard_is_one_grid(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-008

    ``#dash-grid`` *is* the drag scope — SortableJS, the resize button and
    the layout endpoint all key off that id — so "the whole dashboard drags"
    is the claim that every rendered widget is inside it.
    """
    _open_desktop(page, base_url)
    _wait_for_grid_settled(page)

    expect(page.locator("[data-band]")).to_have_count(0)

    in_grid = page.evaluate(
        """() => [...document.querySelectorAll('#dash-grid [data-widget-id]')]
                  .map(e => e.dataset.widgetId)"""
    )
    everywhere = page.evaluate(
        """() => [...document.querySelectorAll('[data-widget-id]')]
                  .map(e => e.dataset.widgetId)"""
    )
    assert in_grid == everywhere, (in_grid, everywhere)

    # The artboard's opening: two half-width cards, then the accent banner.
    assert in_grid[:3] == ["balance_card", "month_card", "wizard_actions"], in_grid
    expect(page.locator('[data-widget-id="balance_card"]')).to_have_attribute("data-cols", "2")
    expect(page.locator('[data-widget-id="month_card"]')).to_have_attribute("data-cols", "2")
    expect(page.locator('[data-widget-id="wizard_actions"]')).to_have_attribute("data-cols", "4")

    # The hero is the phone's answer to a phone question; a wide window that
    # wants it goes and ticks it in Customize.
    assert "safe_to_spend" not in in_grid

    # The width flag selects a rendering, it does not replace one: `1f`'s card
    # of 44px rows and its two-line movements are `KAL-DSH-007`, on the other
    # side of 768px, and a wide window never gets either. Said as absences
    # because this file seeds nothing — whether "Needs attention" has anything
    # to show depends on the ledger, and that the banner is what it shows when
    # it does is `test_wizard_actions_widget.py`, which seeds the items.
    expect(page.locator('[data-widget-id="wizard_actions"] .k-attention-row')).to_have_count(0)
    latest = page.locator('[data-widget-id="recent_transactions"]')
    expect(latest.locator(".k-dash-card")).to_be_visible()
    expect(latest.locator(".k-tx-row")).to_have_count(0)


def test_edit_layout_unlocks_the_whole_grid(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-008"""
    _open_desktop(page, base_url)
    _wait_for_grid_settled(page)

    label = page.locator("#dash-edit-btn-label")
    expect(label).to_be_visible(timeout=10000)
    expect(page.locator("body.dash-editing")).to_have_count(0)

    label.click()

    expect(page.locator("body.dash-editing")).to_have_count(1, timeout=10000)
    expect(label).to_have_text("Done")
    # Every card in the grid is a drag target, not just some band's worth.
    draggable = page.evaluate(
        """() => document.querySelectorAll('#dash-grid .dash-widget-wrap').length"""
    )
    in_grid = page.evaluate(
        """() => document.querySelectorAll('#dash-grid [data-widget-id]').length"""
    )
    assert draggable == in_grid > 0, (draggable, in_grid)

    label.click()
    expect(page.locator("body.dash-editing")).to_have_count(0, timeout=10000)


def test_recent_transactions_dates_rows_month_day(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-009

    The artboard sets `MM-DD`, and ten rows of the same four year digits say
    nothing in a card whose whole claim is that these are the recent ones.
    The cost is a ledger quiet enough for ten rows to cross a new year, so
    the card says where the full date is.
    """
    _open_desktop(page, base_url)
    _wait_for_grid_settled(page)

    card = page.locator('[data-widget-id="recent_transactions"]')
    expect(card).to_be_visible(timeout=10000)
    dates = card.locator(".k-cell-date").all_inner_texts()
    assert dates, "the card rendered no rows"
    assert all(re.fullmatch(r"\d{2}-\d{2}", d.strip()) for d in dates), dates

    expect(card.get_by_role("button", name="View all")).to_be_visible()


def test_a_resize_keeps_every_other_widget(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-008

    The layout POST serialises the grid, and the grid is now the whole
    dashboard — so one resize must not cost the page a card.
    """
    _open_desktop(page, base_url)
    _wait_for_grid_settled(page)
    before = page.evaluate(
        """() => [...document.querySelectorAll('#dash-grid [data-widget-id]')]
                  .map(e => e.dataset.widgetId)"""
    )

    with page.expect_response("**/_dashboard/layout") as response_info:
        page.evaluate("() => window.__kaletaCycleDashSize('cashflow_chart')")
    assert response_info.value.ok, "layout POST did not succeed"

    _open_desktop(page, base_url)
    _wait_for_grid_settled(page)
    after = page.evaluate(
        """() => [...document.querySelectorAll('#dash-grid [data-widget-id]')]
                  .map(e => e.dataset.widgetId)"""
    )
    assert after == before, (before, after)

    # Put the sizes back for the files after this one.
    page.get_by_role("button", name="Customize").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Customize Dashboard", exact=True)).to_be_visible(timeout=5000)
    dialog.get_by_role("button", name="Reset layout").click()
    expect(dialog).to_be_hidden(timeout=10000)
    _wait_for_grid_settled(page)
