# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: an irregular-expenses fund's items and the monthly transfer that feeds it.

Page URL: /wizard/safety-funds/{fund_id}, reached from the fund's card.

Covers: KAL-IRR-001, KAL-IRR-002, KAL-IRR-003
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_reserve_fund

FUND = "Wydatki nieregularne IRR E2E"
FUND_ACCOUNT = "Konto funduszu IRR E2E"
SOURCE = "Konto główne IRR E2E"


def _add_item(page: Page, name: str, yearly: str) -> None:
    page.get_by_role("button", name="Add item").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Item", exact=True).fill(name)
    yearly_field = dialog.get_by_role("spinbutton", name="Yearly amount", exact=True)
    yearly_field.fill(yearly)
    yearly_field.blur()
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Item saved.")).to_be_visible(timeout=5000)


def test_the_fund_plans_its_items_and_the_monthly_transfer(page: Page, base_url: str) -> None:
    """Covers: KAL-IRR-001, KAL-IRR-002, KAL-IRR-003"""
    backing = seed_account(FUND_ACCOUNT)
    seed_account(SOURCE)
    seed_reserve_fund(FUND, 3000.0, backing, kind="irregular", emergency_multiplier=None)

    page.goto(f"{base_url}/wizard/safety-funds")
    card = page.locator(".q-card").filter(has_text=FUND)
    card.get_by_role("button", name="Items").click()
    expect(page).to_have_url(re.compile(r"/wizard/safety-funds/\d+$"), timeout=10000)
    expect(page.get_by_text("Yearly costs", exact=True)).to_be_visible(timeout=10000)

    _add_item(page, "Car insurance", "1200")
    row = page.locator('[data-testid^="irregular-item-"]').filter(has_text="Car insurance")
    expect(row.get_by_test_id("irregular-item-monthly")).to_have_text("120.00")

    _add_item(page, "Property tax", "600")
    expect(page.get_by_test_id("irregular-monthly-total")).to_have_text("180.00")

    expect(
        page.get_by_text(f"Set aside 180.00 every month: a monthly transfer into {FUND_ACCOUNT}.")
    ).to_be_visible()
    page.locator(".q-select").filter(has_text="From account").click()
    page.locator(".q-menu").get_by_text(SOURCE, exact=True).click()
    page.get_by_role("button", name="Create the monthly transfer").click()
    expect(page.get_by_text("Monthly transfer of 180.00 planned.")).to_be_visible(timeout=5000)

    page.goto(f"{base_url}/planned")
    expect(page.get_by_text(FUND, exact=True).first).to_be_visible(timeout=10000)
