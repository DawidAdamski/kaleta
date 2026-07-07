# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Reserve Funds.

Page URL: /wizard/safety-funds
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, update_account


def _fill_number(scope: Page, label: str, value: str) -> None:
    field = scope.get_by_role("spinbutton", name=label, exact=True)
    field.click(click_count=3)
    field.fill(value)


def test_emergency_cash_shows_balance_against_target(page: Page, base_url: str) -> None:
    """Covers: KAL-FND-001

    An emergency reserve fund shows the backing account balance against its target.
    """
    account_name = "Emergency cash FND E2E"
    account_id = seed_account(account_name)
    update_account(account_id, balance="1500.00", type="cash")

    page.goto(f"{base_url}/wizard/safety-funds")
    expect(page.get_by_text("Safety & Reserve Funds", exact=True).first).to_be_visible(timeout=5000)

    page.get_by_role("button", name="Add fund").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_label("Name").fill("Emergency cash FND E2E")
    _fill_number(dialog, "Target amount", "3000")

    dialog.locator(".q-select").filter(has_text="Backing account").click()
    page.locator(".q-menu").get_by_text(account_name, exact=True).click()

    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Emergency cash FND E2E", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("1,500.00 / 3,000.00", exact=True)).to_be_visible(timeout=5000)
