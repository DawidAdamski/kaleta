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
    # and no gutter reserved for it. The palette's pill is the desktop's way
    # in, and the phone's icon is not beside it.
    expect(page.locator("aside.q-drawer")).to_be_hidden()
    expect(page.locator(".k-topnav-search")).to_be_visible()
    expect(page.locator(".k-phone-search")).to_be_hidden()

    # /transactions lives in Capture, so Capture is the section you are in.
    expect(bar.locator('[data-section="nav.group_capture"]')).to_have_attribute(
        "aria-current", "page"
    )
    expect(bar.locator('[data-section="nav.group_setup"]')).not_to_have_attribute(
        "aria-current", "page"
    )

    # The page's name left the header with artboard `1e`; the tab has it.
    assert page.title() == "Transactions · Kaleta", page.title()


def test_the_bar_fits_on_one_line_at_its_narrowest(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-007

    768px is where the bar takes over from the tab bar, and it has five
    sections, two pinned entries, a pill and three icon buttons to fit on one
    60px line. It did not: the row wrapped and "Setup" went under the header.
    The two pinned entries and the pill keep their icons and drop their words
    below 1024px.
    """
    page.set_viewport_size({"width": 768, "height": 900})
    page.goto(f"{base_url}/transactions")
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)

    bar = page.locator(".k-topnav")
    expect(bar).to_be_visible(timeout=10000)
    # Every control in the header, not only the bar's own: the sections fit
    # first and pushed the dark, account and close buttons onto a second line
    # instead, which a 60px header shows by not showing them.
    tops = page.evaluate(
        """() => [...document.querySelectorAll('.k-header > *')]
                  .filter(e => e.getBoundingClientRect().width > 0
                               && !e.classList.contains('q-space'))
                  .map(e => Math.round(e.getBoundingClientRect().top))"""
    )
    assert len(set(tops)) == 1, f"the header wrapped: control tops {sorted(set(tops))}"

    widths = page.evaluate("() => [document.scrollingElement.scrollWidth, window.innerWidth]")
    assert widths[0] <= widths[1], f"page scrolls sideways: {widths[0]} > {widths[1]}"

    # Dropping a word is not dropping the entry: the text stays in the
    # document, so the button keeps its name for anyone not reading pixels.
    expect(bar.locator('[data-nav="nav.wizard"]')).to_contain_text("Financial Wizard")
    # …and every section still reads, because those five are the navigation.
    for _group_key, label in SECTIONS:
        expect(bar.get_by_text(label, exact=True)).to_be_visible()


def test_a_section_menu_routes(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-007"""
    _open_desktop(page, base_url)

    page.locator('.k-topnav [data-section="nav.group_insight"]').click()
    entry = page.locator('[data-nav="nav.net_worth"]')
    expect(entry).to_be_visible(timeout=10000)
    # `q-item` has no `icon` prop, so an entry given one renders bare.
    expect(entry.locator(".q-icon")).to_have_text("pie_chart")
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
    _wait_for_bands_settled(page)

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
                  .map(e => [e.dataset.widgetId, e.dataset.cols, e.dataset.rows])"""
    )
    ids = [wid for wid, _cols, _rows in posted]
    assert "safe_to_spend" in ids
    assert set(in_grid) <= set(ids)
    # …and each of them with a size the endpoint will accept. A node with no
    # size posts as 1x1, which none of the banded widgets allows.
    assert all(cols and rows for _wid, cols, rows in posted), posted


def _post_layout(page: Page, entries: list[dict[str, object]]) -> None:
    """Persist *entries* through the endpoint the drag handler posts to."""
    with page.expect_response("**/_dashboard/layout") as response_info:
        page.evaluate(
            """(entries) => fetch('/_dashboard/layout', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({entries}),
            })""",
            entries,
        )
    assert response_info.value.ok, "layout POST did not succeed"


def test_a_month_band_with_nothing_in_it_still_says_so(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-008

    Customize will happily leave the Month band empty — one widget overall is
    all it insists on. Every other band is skipped when empty, but Month is
    the drag scope and the empty state: without it the page loses the grid,
    the Edit button and the only line telling you where the widgets went.
    """
    _open_desktop(page, base_url)
    page.wait_for_selector("#dash-grid", timeout=20000)
    _post_layout(page, [{"id": "recent_transactions", "cols": 4, "rows": 2}])

    _open_desktop(page, base_url)
    month = page.locator('[data-band="month"]')
    expect(month).to_be_visible(timeout=20000)
    expect(month.locator("#dash-grid")).to_be_visible()
    expect(month.locator("[data-widget-id]")).to_have_count(0)
    expect(month.get_by_text("No widgets here. Open Customize to add one.")).to_be_visible()
    expect(month.locator("#dash-edit-btn-label")).to_be_visible()

    # Leave the shared storage back at its defaults for the files after this.
    page.get_by_role("button", name="Customize").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Customize Dashboard", exact=True)).to_be_visible(timeout=5000)
    dialog.get_by_role("button", name="Reset widgets").click()
    expect(dialog).to_be_hidden(timeout=10000)
    page.wait_for_selector("#dash-grid [data-widget-id]", timeout=20000)


def _wait_for_bands_settled(page: Page) -> None:
    """Block until NiceGUI has finished streaming widgets into the bands.

    Widgets arrive one at a time over the websocket, and the layout POST
    serialises *whatever is in the DOM right now* — fire it mid-stream and it
    persists a dashboard missing every widget yet to arrive. Wait for the
    count to hold steady rather than guessing at a sleep.
    """
    page.wait_for_function(
        """() => {
          const bands = document.getElementById('dash-bands');
          if (!bands) return false;
          const n = bands.querySelectorAll('[data-widget-id]').length;
          const s = window.__kaletaBandSettle || {count: -1, stable: 0};
          s.stable = n > 0 && n === s.count ? s.stable + 1 : 0;
          s.count = n;
          window.__kaletaBandSettle = s;
          return s.stable >= 3;
        }""",
        polling=200,
        timeout=30000,
    )


def test_a_resize_in_month_does_not_delete_the_other_bands(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-008

    The layout POST serialises every banded widget, not just the Month
    grid's — so every banded widget has to survive the round trip. It did
    not: a widget outside the grid carried no ``data-cols``, posted as 1x1,
    and 1x1 is a size none of them allows. The first resize or drag deleted
    the hero, the banner and the Latest list from storage, and the page came
    back without them.
    """
    _open_desktop(page, base_url)
    _wait_for_bands_settled(page)

    with page.expect_response("**/_dashboard/layout") as response_info:
        page.evaluate("() => window.__kaletaCycleDashSize('cashflow_chart')")
    assert response_info.value.ok, "layout POST did not succeed"

    _open_desktop(page, base_url)
    page.wait_for_selector("#dash-bands", timeout=20000)
    expect(page.locator('[data-band="now"] [data-widget-id="safe_to_spend"]')).to_have_count(1)
    expect(
        page.locator('[data-band="latest"] [data-widget-id="recent_transactions"]')
    ).to_have_count(1)

    # Put the sizes back for the files after this one.
    page.get_by_role("button", name="Customize").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Customize Dashboard", exact=True)).to_be_visible(timeout=5000)
    dialog.get_by_role("button", name="Reset layout").click()
    expect(dialog).to_be_hidden(timeout=10000)
