# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for the phone dashboard and its tab bar (artboard 1f).

Covers: KAL-NAV-006, KAL-DSH-007

Most of these seed nothing. The suite shares one database and one user
storage, so a test that adds rows changes what every later file sees — and
the claims here are about the navigation a narrow viewport gets and the
shape the widgets are drawn in, which hold on an empty ledger and on a full
one. The one exception is the redraw test below: "the Latest band is rows,
not a table" and "Needs attention is a card of rows, not a banner" are
claims about rows, so that test seeds one of each and says so.
"""

from __future__ import annotations

import datetime
import re

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    get_or_seed_category,
    seed_account,
    seed_personal_loan,
    seed_transaction,
)

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

    A 390px header has room for one way into the palette. The wide window's
    "Jump to…" pill and the mini toggle beside it are both desktop controls,
    and both carry their own breakpoint rather than a `hidden md:` utility.
    """
    _open_phone_dashboard(page, base_url)

    expect(page.locator(".k-phone-search")).to_be_visible(timeout=10000)
    expect(page.locator(".k-header-search")).to_be_hidden()
    expect(page.locator("[data-drawer-mini-toggle]")).to_be_hidden()


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
    neither: a shut drawer and no tab bar. `breakpoint=767` is what makes the
    two agree — below 768px the tab bar, above it the docked drawer, and
    never a window with neither.
    """
    page.set_viewport_size({"width": 900, "height": 900})
    page.goto(f"{base_url}/transactions")
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)

    expect(page.locator("aside.q-drawer")).to_be_visible(timeout=10000)
    expect(page.locator(".k-tabbar")).to_be_hidden()


def test_the_phone_dashboard_stacks_into_bands(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-007"""
    _open_phone_dashboard(page, base_url)
    _reset_widgets(page)
    _open_phone_dashboard(page, base_url)

    for band, heading in (
        ("month", "This month"),
        ("watch", "Watch"),
        ("latest", "Latest"),
    ):
        section = page.locator(f'[data-band="{band}"]')
        expect(section).to_be_visible(timeout=10000)
        expect(section.get_by_text(heading, exact=True).first).to_be_visible()

    # Nothing above the answer: no page title, and no heading over the first
    # band either. Artboard `1f` opens on the figure, and every word before
    # it is a word between the reader and it.
    expect(page.locator(".k-page-title")).to_have_count(0)
    now = page.locator('[data-band="now"]')
    expect(now).to_be_visible(timeout=10000)
    expect(now.get_by_text("Now", exact=True)).to_have_count(0)
    expect(now.locator("[data-widget-id]").first).to_have_attribute(
        "data-widget-id", "safe_to_spend", timeout=10000
    )
    # The eyebrow carries the question and its denominator on one line.
    expect(now.locator(".k-eyebrow").first).to_contain_text("Safe to spend")
    expect(now.locator(".k-eyebrow").first).to_contain_text("left")
    # Pace and habit in one sentence, under the figure. The artboard puts it
    # there and the split bar below it — but an empty ledger has no bar to
    # draw (three zero-width segments), so the order is asserted against the
    # figure, which is always there, and against the bar only when there is
    # one. `1f.md` carries the measured offsets on a seeded ledger.
    rate = now.locator(".k-hero-rate")
    expect(rate).to_be_visible()
    rate_y = rate.bounding_box()["y"]
    assert rate_y > now.locator(".k-ink.k-mono").first.bounding_box()["y"]
    bar = now.locator(".k-split--hero")
    if bar.count():
        assert rate_y < bar.bounding_box()["y"]

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

    # The hero is off by default — it is a phone answer to a phone question,
    # and the desktop grid does not carry it — so the phone prepends it
    # rather than waiting for the user to tick a box they cannot see here.
    page.get_by_role("button", name="Customize").click()
    dialog = page.get_by_role("dialog")
    hero_row = dialog.locator('[data-customize-row="safe_to_spend"]')
    expect(hero_row).to_be_visible(timeout=5000)
    expect(hero_row.locator('[role="checkbox"]')).to_have_attribute(
        "aria-checked", "false", timeout=5000
    )
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden(timeout=10000)

    widths = page.evaluate("() => [document.scrollingElement.scrollWidth, window.innerWidth]")
    assert widths[0] <= widths[1], f"page scrolls sideways: {widths[0]} > {widths[1]}"


def test_a_wide_window_does_not_get_the_phone_layout(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-007

    The phone layout is chosen once, server-side, from the viewport width —
    so the guard that a wide window still gets the grid belongs next to the
    test that a narrow one does not. What the wide window does with that grid
    is KAL-DSH-008, in ``test_dashboard_desktop.py``.
    """
    page.set_viewport_size({"width": 1360, "height": 900})
    page.goto(f"{base_url}/")
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)

    expect(page.locator("#dash-grid")).to_be_visible(timeout=20000)
    expect(page.locator(".k-tabbar")).to_be_hidden()


def _computed(page: Page, selector: str, prop: str) -> str:
    return str(
        page.evaluate(
            "([sel, prop]) => getComputedStyle(document.querySelector(sel)).getPropertyValue(prop)",
            [selector, prop],
        )
    ).strip()


def test_the_phone_redraws_the_widgets_that_do_not_fit(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-007

    Artboard `1f` draws four of the catalogue differently at 390px, and
    until now a widget could not tell: its render signature was
    ``(session, is_dark)``. Each claim below is about the *shape* the widget
    took, which is the thing `RenderContext.narrow` bought.
    """
    today = datetime.date.today()
    seed_personal_loan("Phone band overdue", 210.0, due_at=today - datetime.timedelta(days=2))
    account = seed_account("Phone band account")
    category = get_or_seed_category("Phone band category")
    seed_transaction(account, category, 128.74, date=today, description="Lidl phone band")

    _open_phone_dashboard(page, base_url)
    _reset_widgets(page)
    _open_phone_dashboard(page, base_url)

    # ── The hero, flat on the ground (`1f.md` row 7b) ──────────────────────
    hero = page.locator('[data-widget-id="safe_to_spend"]')
    expect(hero).to_be_visible(timeout=10000)
    expect(hero.locator(".k-dash-card")).to_have_count(0)
    expect(hero.locator(".k-hero-rate")).to_be_visible()

    # ── Needs attention: a paper card of 44px rows, not the banner (row 10) ─
    attention = page.locator('[data-widget-id="wizard_actions"]')
    expect(attention).to_be_visible(timeout=10000)
    expect(attention.locator(".k-banner")).to_have_count(0)
    expect(attention.locator(".k-dash-card")).to_be_visible()
    rows = attention.locator(".k-attention-row")
    expect(rows.first).to_be_visible(timeout=10000)
    box = rows.first.bounding_box()
    assert box is not None
    assert box["height"] >= MIN_TAP_TARGET, box
    # The severity the banner carries in a glyph is carried by the order here,
    # so the attribute the ranking test reads has to survive the redraw.
    expect(rows.first).to_have_attribute("data-severity", re.compile(r"danger|warning|info"))
    expect(attention.locator(".k-attention-dot").first).to_be_visible()
    expect(attention.locator(".k-attention-count")).to_be_visible()

    # ── The Month band: bare type over a 120px chart (row 11) ──────────────
    month = page.locator('[data-widget-id="month_card"]')
    expect(month).to_be_visible(timeout=10000)
    expect(month.locator(".k-dash-card")).to_have_count(0)
    # 500/18 mono, which is the size `1f` sets for a figure on the ground.
    assert _computed(page, '[data-widget-id="month_card"] .k-mono', "font-size") == "18px"
    # The pace bar and the two footer figures are the wide card's; the Watch
    # band two bands down already says all three.
    expect(month.locator(".k-pace")).to_have_count(0)

    chart = page.locator('[data-widget-id="cashflow_chart"]')
    expect(chart).to_be_visible(timeout=10000)
    expect(chart.locator(".k-dash-card")).to_have_count(0)
    chart_box = chart.locator(".nicegui-echart").bounding_box()
    assert chart_box is not None
    assert round(chart_box["height"]) == 120, chart_box

    # ── Latest: two-line rows, not five columns (row 13) ───────────────────
    latest = page.locator('[data-widget-id="recent_transactions"]')
    expect(latest).to_be_visible(timeout=10000)
    expect(latest.locator(".k-dash-card")).to_have_count(0)
    expect(latest.locator("table")).to_have_count(0)
    # The band's heading is the list's title, so the widget adds none — and
    # with the title line goes the "View all" the wide card carries on it.
    expect(latest.get_by_role("button", name="View all")).to_have_count(0)
    tx_rows = latest.locator(".k-tx-row")
    expect(tx_rows.first).to_be_visible(timeout=10000)
    tx_box = tx_rows.first.bounding_box()
    assert tx_box is not None
    assert tx_box["height"] >= 52, tx_box
    # "03.07 · Żywność" — day before month, which is what `1f` writes. The
    # wide window's table keeps `1c`'s month-day (`KAL-DSH-009`).
    meta = latest.locator(".k-tx-meta").first.inner_text().strip()
    assert re.match(r"^\d{2}\.\d{2}( · .+)?$", meta), meta

    widths = page.evaluate("() => [document.scrollingElement.scrollWidth, window.innerWidth]")
    assert widths[0] <= widths[1], f"page scrolls sideways: {widths[0]} > {widths[1]}"
