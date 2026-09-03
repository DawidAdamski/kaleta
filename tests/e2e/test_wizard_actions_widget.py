# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Wizard Action Items.

Covers: KAL-WAC-002, KAL-WAC-003, KAL-WAC-004

Seeds one item per severity band and checks the dashboard widget renders
them ranked, with working row links.
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_personal_loan, seed_subscription

_WIDGET = '[data-widget-id="wizard_actions"]'


def test_widget_ranks_items_and_links_rows(page: Page, base_url: str) -> None:
    """Covers: KAL-WAC-002, KAL-WAC-003, KAL-WAC-004

    An overdue loan (danger), a loan due in 3 days (warning) and a
    past-due subscription renewal (info) appear in that order, and the
    subscription row routes to its focused page.
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
