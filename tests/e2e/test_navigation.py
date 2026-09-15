# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Navigation (workflow-based sidebar).

Covers: KAL-NAV-001, KAL-NAV-002, KAL-NAV-004, KAL-NAV-005

Guards the Phase A regroup from docs/ux/feature-categorization-audit.md:
pinned Dashboard/Wizard entries, workflow groups, Setup collapsed by
default, and every sidebar entry routing to its page.
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# (group label, [(item label, path), ...]) — mirrors NAV_GROUPS in views/layout.py.
GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Capture", [("Transactions", "/transactions"), ("Import", "/import")]),
    (
        "Monthly cycle",
        [
            ("Budgets", "/budgets"),
            ("Payment Calendar", "/payment-calendar"),
            ("Monthly Readiness", "/wizard/monthly-readiness"),
            ("Subscriptions", "/wizard/subscriptions"),
        ],
    ),
    (
        "Plans & funds",
        [
            ("Annual Plan", "/budget-plan"),
            ("Safety Funds", "/wizard/safety-funds"),
            ("Personal Loans", "/wizard/personal-loans"),
        ],
    ),
    (
        "Insight",
        [
            ("Reports", "/reports"),
            ("Net Worth", "/net-worth"),
            ("Forecast", "/forecast"),
            ("Credit", "/credit"),
            ("Credit Calculator", "/credit-calculator"),
        ],
    ),
    (
        "Setup",
        [
            ("Accounts", "/accounts"),
            ("Institutions", "/institutions"),
            ("Categories", "/categories"),
            ("Tags", "/tags"),
            ("Payees", "/payees"),
            ("Rules", "/rules"),
            ("Housekeeping", "/housekeeping"),
            ("Settings", "/settings"),
        ],
    ),
]

PINNED: list[tuple[str, str]] = [("Dashboard", "/"), ("Financial Wizard", "/wizard")]


def _drawer(page: Page) -> Locator:
    return page.locator("aside.q-drawer")


def _connected(page: Page) -> None:
    """Wait until this document's socket has finished its NiceGUI handshake.

    A nav entry is clickable as soon as Vue mounts, which is before the
    socket is up; an event fired in that window is queued client-side and
    only replayed once the socket connects. Waiting for the handshake means
    the click is going to a client that is already live.
    """
    page.wait_for_function("() => window.did_handshake === true", timeout=20000)


def _click_nav(page: Page, label: str, path: str, base_url: str) -> None:
    """Click one drawer entry and assert it lands on its page.

    A nav entry is a ``ui.item`` with a *server-side* handler: the click
    travels to the server, which answers with a navigate message. That round
    trip occasionally does not complete — a socket that drops between the two
    halves leaves the page sitting where it was, most often on the first
    click after a fresh document — and the whole run then fails on whichever
    entry happened to be first. One retry covers a dropped round trip; the
    URL assertion below it is unchanged, so a genuinely broken route still
    fails here as loudly as before.
    """
    entry = _drawer(page).get_by_text(label, exact=True)
    expect(entry).to_be_visible(timeout=10000)
    entry.click()
    try:
        page.wait_for_url(f"{base_url}{path}", timeout=5000)
    except PlaywrightTimeoutError:
        _connected(page)
        _drawer(page).get_by_text(label, exact=True).click()
    expect(page).to_have_url(f"{base_url}{path}", timeout=10000)


def _ensure_group_expanded(page: Page, group_label: str, probe_item: str) -> None:
    """Expand a collapsed nav group by clicking its header (no-op when expanded).

    ``is_visible`` reads the DOM as it stands *now*, so it must not run while
    the drawer is still being streamed in after a navigation: an expanded
    group that has not arrived yet probes as collapsed, the header click then
    *collapses* it, and the item click that follows times out on an element
    that is present but hidden. Waiting for the header first is what makes
    the probe answer a question about the finished drawer.
    """
    drawer = _drawer(page)
    header = drawer.get_by_text(group_label, exact=True)
    expect(header).to_be_visible(timeout=10000)
    probe = drawer.get_by_text(probe_item, exact=True)
    if not probe.is_visible():
        header.click()
        expect(probe).to_be_visible(timeout=5000)


def test_sidebar_shows_pinned_and_groups(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-001"""
    page.goto(f"{base_url}/")
    drawer = _drawer(page)
    for label, _path in PINNED:
        expect(drawer.get_by_text(label, exact=True)).to_be_visible(timeout=10000)
    for group_label, _items in GROUPS:
        expect(drawer.get_by_text(group_label, exact=True)).to_be_visible()


def test_setup_group_collapsed_by_default(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-002

    Runs before the routing loop below (pytest keeps in-file order), so the
    per-session storage still has no stored collapse choice for Setup.
    """
    page.goto(f"{base_url}/")
    drawer = _drawer(page)
    expect(drawer.get_by_text("Setup", exact=True)).to_be_visible(timeout=10000)
    expect(drawer.get_by_text("Institutions", exact=True)).to_be_hidden()
    drawer.get_by_text("Setup", exact=True).click()
    expect(drawer.get_by_text("Institutions", exact=True)).to_be_visible(timeout=5000)


def test_every_nav_entry_routes(page: Page, base_url: str) -> None:
    """Covers: KAL-NAV-004, KAL-NAV-005

    Clicks every sidebar entry (pinned + all groups, expanding collapsed
    groups first) and asserts the URL changes to the entry's page.
    """
    page.goto(f"{base_url}/")
    for label, path in PINNED:
        _connected(page)
        _click_nav(page, label, path, base_url)
    for group_label, items in GROUPS:
        for label, path in items:
            _connected(page)
            _ensure_group_expanded(page, group_label, items[0][0])
            _click_nav(page, label, path, base_url)
