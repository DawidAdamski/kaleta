# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Single-user authentication.

Covers: KAL-AUTH-001, KAL-AUTH-002, KAL-AUTH-003, KAL-AUTH-004, KAL-AUTH-005,
KAL-AUTH-006, KAL-AUTH-011, KAL-AUTH-012
"""

from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from tests.e2e.conftest import E2E_PASSWORD, E2E_USERNAME


def test_login_success(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-001"""
    page_no_auth.goto(f"{base_url}/login")
    page_no_auth.get_by_label("Username", exact=True).fill(E2E_USERNAME)
    page_no_auth.get_by_label("Password", exact=True).fill(E2E_PASSWORD)
    page_no_auth.get_by_role("button", name="Log in").click()

    expect(page_no_auth).not_to_have_url(f"{base_url}/login", timeout=10000)
    page_no_auth.goto(f"{base_url}/")
    expect(page_no_auth.get_by_text("Dashboard", exact=True).first).to_be_visible(timeout=10000)


def test_login_wrong_password(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-002"""
    page_no_auth.goto(f"{base_url}/login")
    page_no_auth.get_by_label("Username", exact=True).fill(E2E_USERNAME)
    page_no_auth.get_by_label("Password", exact=True).fill("definitely-wrong")
    page_no_auth.get_by_role("button", name="Log in").click()

    expect(page_no_auth).to_have_url(f"{base_url}/login", timeout=5000)
    expect(page_no_auth.get_by_text("Invalid username or password.")).to_be_visible(timeout=5000)


def test_failed_login_does_not_move_the_button(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-011

    The message used to be a label that appeared, which pushed the button
    down by its own height at the moment the user was reaching for it again —
    so the second attempt landed on nothing.
    """
    page_no_auth.goto(f"{base_url}/login")
    button = page_no_auth.get_by_role("button", name="Log in")
    expect(button).to_be_visible(timeout=10000)
    before = button.bounding_box()
    assert before is not None

    page_no_auth.get_by_label("Username", exact=True).fill(E2E_USERNAME)
    page_no_auth.get_by_label("Password", exact=True).fill("definitely-wrong-too")
    button.click()

    expect(page_no_auth.get_by_text("Invalid username or password.")).to_be_visible(timeout=5000)
    after = button.bounding_box()
    assert after is not None
    assert after["y"] == before["y"], (
        f"the button moved from y={before['y']} to y={after['y']} when the message appeared"
    )


def test_login_panel_counts_and_says_nothing_more(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-012

    The panel is read before anyone has proved who they are. Counts are a
    deliberate decision (`AUTH_PANEL_STATS`); an amount, a name or a payee
    leaking onto it would not be.

    Nothing is seeded here on purpose: the suite shares one database and this
    runs first, so an account created for this test would lengthen the
    account pickers every later test has to choose from. By the time it runs
    the ledger has whatever earlier runs left in it, and what is asserted is
    that the panel shows counts and nothing else whatever is in there.
    """
    page_no_auth.set_viewport_size({"width": 1360, "height": 900})
    page_no_auth.goto(f"{base_url}/login")
    panel = page_no_auth.locator(".k-auth-panel")
    expect(panel).to_be_visible(timeout=10000)

    figures = panel.locator(".k-auth-figure")
    expect(figures).to_have_count(3)
    labels = ["Transactions", "Accounts", "Months of history"]
    for label in labels:
        expect(panel.get_by_text(label, exact=True)).to_be_visible()

    # Whatever the panel says, it is the copy, the three labels and three
    # plain integers — take those away and there must be nothing left. That
    # is a stronger claim than hunting for particular leaks, and it needs no
    # data of its own to make it.
    # Case-folded: the labels are uppercased by CSS, so what comes back from
    # the DOM is not the string the locale file holds.
    remaining = panel.inner_text().casefold()
    for label in labels:
        remaining = remaining.replace(label.casefold(), "", 1)
    for index in range(3):
        figure = figures.nth(index).inner_text()
        assert figure.replace("\u00a0", "").replace(" ", "").isdigit(), figure
        remaining = remaining.replace(figure.casefold(), "", 1)
    copy_line = "Your ledger, on your own machine. No cloud account, no one else reading it."
    assert copy_line.casefold() in remaining
    remaining = remaining.replace(copy_line.casefold(), "", 1)
    assert remaining.strip() == "", f"the panel says more than counts: {remaining!r}"


def test_guard_redirects_unauthenticated_deep_link(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-003"""
    page_no_auth.goto(f"{base_url}/transactions")

    expect(page_no_auth).to_have_url(f"{base_url}/login?redirect_to=/transactions", timeout=10000)


def test_guard_redirects_unauthenticated_setup(page_no_auth: Page, base_url: str) -> None:
    """Covers: KAL-AUTH-004"""
    page_no_auth.goto(f"{base_url}/setup")

    expect(page_no_auth).to_have_url(f"{base_url}/login?redirect_to=/setup", timeout=10000)


def test_api_unauthorized_without_token(base_url: str) -> None:
    """Covers: KAL-AUTH-005"""
    resp = httpx.get(f"{base_url}/api/v1/accounts/", timeout=10.0)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_api_authorized_with_bearer_token(base_url: str, e2e_api_token: str) -> None:
    """Covers: KAL-AUTH-006"""
    resp = httpx.get(
        f"{base_url}/api/v1/accounts/",
        headers={"Authorization": f"Bearer {e2e_api_token}"},
        timeout=10.0,
    )
    assert resp.status_code == 200
