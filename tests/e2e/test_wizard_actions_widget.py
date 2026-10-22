# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Wizard Action Items.

Covers: KAL-WAC-002, KAL-WAC-003, KAL-WAC-004, KAL-DSH-008, KAL-DSH-012

Seeds one item per severity band and checks the dashboard widget renders
them ranked, with working row links, and that a banner item is a control
reachable and activated from the keyboard.
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Locator, Page, expect

from tests.e2e.seed_helpers import seed_personal_loan, seed_subscription

_WIDGET = '[data-widget-id="wizard_actions"]'


def test_widget_ranks_items_and_links_rows(page: Page, base_url: str) -> None:
    """Covers: KAL-WAC-002, KAL-WAC-003, KAL-WAC-004, KAL-DSH-008

    An overdue loan (danger), a loan due in 3 days (warning) and a
    past-due subscription renewal (info) appear in that order, and the
    subscription row routes to its focused page.

    It is also the one place in the suite where the widget is wide *and*
    has something to show, so it is where "a wide window still gets the
    accent banner" can be a claim rather than a coincidence.
    """
    today = datetime.date.today()
    seed_personal_loan("Overdue WAC E2E", 500.0, due_at=today - datetime.timedelta(days=1))
    seed_personal_loan("Soon WAC E2E", 300.0, due_at=today + datetime.timedelta(days=3))
    sub_id = seed_subscription(
        "Netflix WAC E2E",
        43.0,
        next_expected_at=today - datetime.timedelta(days=2),
    )

    page.goto(f"{base_url}/")
    widget = page.locator(_WIDGET)
    expect(widget).to_be_visible(timeout=10000)

    # The wide window's rendering is artboard `1c`'s accent banner. `1f`'s
    # paper card of 44px rows is the phone's (`KAL-DSH-007`), and the width
    # selects between them rather than replacing one with the other.
    expect(widget.locator(".k-banner")).to_have_count(1)
    expect(widget.locator(".k-attention-row")).to_have_count(0)

    # ── KAL-WAC-003: severity follows urgency ─────────────────────────────
    overdue_row = widget.locator('[data-action-kind="loan_overdue"]')
    due_soon_row = widget.locator('[data-action-kind="loan_due_soon"]')
    expect(overdue_row.first).to_have_attribute("data-severity", "danger", timeout=10000)
    expect(due_soon_row.first).to_have_attribute("data-severity", "warning")

    # ── KAL-WAC-004: danger, then warning, then info ──────────────────────
    severities = widget.locator("[data-severity]").evaluate_all(
        "els => els.map(e => e.dataset.severity)"
    )
    rank = {"danger": 0, "warning": 1, "info": 2}
    assert severities, "widget rendered no action rows"
    assert severities == sorted(severities, key=lambda s: rank[s]), severities

    # ── KAL-WAC-002: the subscription row links to its focused page ───────
    sub_row = widget.locator('[data-action-kind="subscription_renewal_due"]').first
    expect(sub_row).to_have_attribute("data-severity", "info")
    sub_row.click()
    page.wait_for_url(f"**/wizard/subscriptions?focus={sub_id}", timeout=10000)


def test_desktop_banner_item_is_keyboard_reachable_and_activated(page: Page, base_url: str) -> None:
    """Covers: KAL-DSH-012

    A desktop "Needs attention" banner item is a real control, not a
    pointer-only row: it is in the tab order, announced as a button, and
    Enter and Space each navigate to the exact page a click opens — the fix
    ``_row_element`` (commit ab2cac0) already carries for the phone rows.

    Asserts on an overdue personal loan (danger), which always ranks first
    and so stays within the banner's 12 visible rows even when the shared
    session has saturated it — unlike an info-severity renewal, which sits
    in the tail. Defined after ``test_widget_ranks_items_and_links_rows`` so
    the seed added here cannot perturb that sibling's view of the banner.
    """
    counterparty = "Overdue DSH012 E2E"
    loan_id = seed_personal_loan(
        counterparty, 700.0, due_at=datetime.date.today() - datetime.timedelta(days=1)
    )
    href = f"/wizard/personal-loans?focus={loan_id}"

    page.set_viewport_size({"width": 1360, "height": 900})
    page.goto(f"{base_url}/")

    widget = page.locator(_WIDGET)
    expect(widget).to_be_visible(timeout=10000)
    # The wide rendering is the accent banner, not the phone's paper rows.
    expect(widget.locator(".k-banner")).to_have_count(1)

    # Scope to this loan's own row: the ranks test seeds another overdue loan
    # into the same shared session, so the kind alone is not unique — the
    # title carries the counterparty name, which is.
    def _row() -> Locator:
        return widget.locator('.k-banner-item[data-action-kind="loan_overdue"]').filter(
            has_text=counterparty
        )

    row = _row()
    expect(row).to_be_visible(timeout=10000)

    # It is a control: announced as a button and in the tab order.
    expect(row).to_have_attribute("role", "button")
    expect(row).to_have_attribute("tabindex", "0")

    # Enter activates it, going to the same focused page a click would.
    row.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(f"**{href}", timeout=10000)

    # Space activates it too — the second key a role="button" promises.
    page.goto(f"{base_url}/")
    expect(widget).to_be_visible(timeout=10000)
    row = _row()
    expect(row).to_be_visible(timeout=10000)
    row.focus()
    page.keyboard.press(" ")
    page.wait_for_url(f"**{href}", timeout=10000)
