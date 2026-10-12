# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E: an irregular-expenses fund's items and the monthly transfer that feeds it.

Page URL: /wizard/safety-funds/{fund_id}, reached from the fund's card.

Covers: KAL-IRR-001, KAL-IRR-002, KAL-IRR-003, KAL-IRR-004, KAL-IRR-005
"""

from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e.seed_helpers import seed_account, seed_category, seed_reserve_fund, update_account

FUND = "Wydatki nieregularne IRR E2E"
FUND_ACCOUNT = "Konto funduszu IRR E2E"
SOURCE = "Konto główne IRR E2E"
PAID_ON = "2024-01-15"


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
    seed_reserve_fund(FUND, 0.0, backing, kind="irregular", emergency_multiplier=None)

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


def _fund_page(page: Page, base_url: str, fund: str, account: str, balance: str) -> None:
    backing = seed_account(account)
    update_account(backing, balance=balance)
    # No target: a fund below one is a dashboard warning, and this shared
    # instance's wizard widget has other tests' warnings to rank.
    seed_reserve_fund(fund, 0.0, backing, kind="irregular", emergency_multiplier=None)
    page.goto(f"{base_url}/wizard/safety-funds")
    page.locator(".q-card").filter(has_text=fund).get_by_role("button", name="Items").click()
    expect(page.get_by_test_id("irregular-balance")).to_have_text(
        f"{float(balance):,.2f}", timeout=10000
    )


def _pick(page: Page, scope: Locator, label: str, option: str, *, typed: bool = False) -> None:
    select = scope.locator(".q-select").filter(has_text=label)
    select.click()
    if typed:
        # The shared instance holds every test's categories: filter, do not scroll.
        select.locator("input").fill(option)
    page.locator(".q-menu").get_by_text(option, exact=True).click()


def _record_payment(page: Page, amount: str, *, item: str | None = None, **fields: str) -> None:
    page.get_by_role("button", name="Record a payment").click()
    dialog = page.get_by_role("dialog")
    if item is not None:
        _pick(page, dialog, "Paid for", item)
    dialog.get_by_role("spinbutton", name="Amount", exact=True).fill(amount)
    # Long ago, so these rows sit below every other test's recent ones.
    dialog.get_by_label("Date", exact=True).fill(PAID_ON)
    if "description" in fields:
        dialog.get_by_label("Description", exact=True).fill(fields["description"])
    if "category" in fields:
        _pick(page, dialog, "Category", fields["category"], typed=True)
    dialog.get_by_role("button", name="Record").click()
    expect(page.get_by_text("Payment recorded.")).to_be_visible(timeout=5000)


def test_paying_an_item_from_the_fund(page: Page, base_url: str) -> None:
    """Covers: KAL-IRR-004"""
    seed_category("Ubezpieczenia IRR4 E2E", cat_type="expense")
    _fund_page(page, base_url, "Fundusz IRR4 E2E", "Konto IRR4 E2E", "1500.00")
    page.get_by_role("button", name="Add item").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Item", exact=True).fill("Car insurance")
    dialog.get_by_role("spinbutton", name="Yearly amount", exact=True).fill("1200")
    _pick(page, dialog, "Category for its payments", "Ubezpieczenia IRR4 E2E", typed=True)
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Item saved.")).to_be_visible(timeout=5000)

    _record_payment(page, "1250", item="Car insurance")

    expect(page.get_by_test_id("irregular-balance")).to_have_text("250.00", timeout=10000)
    entry = page.locator('[data-testid^="irregular-entry-"]').filter(has_text="-1,250.00")
    expect(entry.get_by_test_id("irregular-paid-for")).to_contain_text("Car insurance")
    expect(entry.get_by_test_id("irregular-unplanned")).to_have_count(0)


def test_an_unplanned_cost_paid_from_the_fund(page: Page, base_url: str) -> None:
    """Covers: KAL-IRR-005"""
    seed_category("Ogrzewanie IRR5 E2E", cat_type="expense")
    _fund_page(page, base_url, "Fundusz IRR5 E2E", "Konto IRR5 E2E", "800.00")

    _record_payment(page, "300", description="heating underpayment", category="Ogrzewanie IRR5 E2E")

    expect(page.get_by_test_id("irregular-balance")).to_have_text("500.00", timeout=10000)
    entry = page.locator('[data-testid^="irregular-entry-"]').filter(
        has_text="heating underpayment"
    )
    expect(entry.get_by_test_id("irregular-unplanned")).to_have_text("Unplanned")
