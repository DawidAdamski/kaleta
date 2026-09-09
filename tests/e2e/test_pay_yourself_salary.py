# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E smoke tests for the "Pay yourself a salary" wizard panel.

Page URL: /wizard/pay-yourself

The panel aggregates income across every account, and the e2e instance shares
one database between all modules — so the numbers on screen depend on what
other tests seeded. The arithmetic of Feature: Pay Yourself a Salary is pinned
against a fixed window in ``tests/integration/test_pay_yourself_salary.py``;
what is checked here is that the tile now opens a page that renders the panel
end to end.
"""

from __future__ import annotations

import datetime

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_income_category, seed_transaction


def _tenth_of_month(months_back: int) -> datetime.date:
    """The 10th of the month ``months_back`` complete months before this one."""
    today = datetime.date.today()
    index = today.year * 12 + (today.month - 1) - months_back
    return datetime.date(index // 12, index % 12 + 1, 10)


@pytest.fixture(scope="module", autouse=True)
def irregular_income(base_url: str) -> None:
    """Four complete months of invoices — enough history for a proposal.

    Module-scoped: the e2e database is shared, so seeding once keeps the
    category name unique and the totals stable across both tests.
    """
    account_id = seed_account("Freelance business SAL E2E")
    category_id = seed_income_category("Invoices SAL E2E")
    for months_back, amount in ((4, 6000.0), (3, 9000.0), (2, 4000.0), (1, 12000.0)):
        seed_transaction(
            account_id,
            category_id,
            amount,
            tx_type="income",
            date=_tenth_of_month(months_back),
            description="invoice",
        )


def test_panel_renders_the_proposal_and_the_action(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/wizard/pay-yourself")

    expect(page.get_by_text("Pay yourself a salary", exact=True).first).to_be_visible(timeout=5000)
    expect(page.get_by_text("How much your income swings", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Worst month", exact=True)).to_be_visible()
    expect(page.get_by_text("Best month", exact=True)).to_be_visible()
    expect(page.get_by_text("Buffer projection", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Create monthly transfer")).to_be_visible()


def test_wizard_tile_opens_the_panel(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/wizard")
    tile = page.get_by_text("Pay yourself a salary", exact=True)
    row = tile.locator("xpath=ancestor::div[contains(@class,'items-start')][1]")
    expect(row.get_by_text("Coming soon")).to_have_count(0)
    row.get_by_role("button", name="Open").click()

    page.wait_for_url(f"{base_url}/wizard/pay-yourself", timeout=10000)
    expect(page.get_by_text("Proposed salary", exact=True)).to_be_visible(timeout=5000)
