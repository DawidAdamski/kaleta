# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Payee Identities.

Page URL: /reports/top-merchants (Top payees by spend).
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_category, seed_payee, seed_transaction


def test_top_payees_report_ranks_by_spend(page: Page, base_url: str) -> None:
    """Covers: KAL-PID-003

    Given transactions across several payees exist, the Top Merchants report
    ranks payees by total amount spent in the selected period.
    """
    account_id = seed_account("PID Report E2E")
    category_id = seed_category("PID Food E2E")
    lidl_id = seed_payee("Lidl PID E2E")
    biedronka_id = seed_payee("Biedronka PID E2E")

    today = datetime.date.today()
    seed_transaction(
        account_id,
        category_id,
        200.0,
        date=today,
        payee_id=lidl_id,
        description="Lidl shop",
    )
    seed_transaction(
        account_id,
        category_id,
        75.0,
        date=today,
        payee_id=biedronka_id,
        description="Biedronka shop",
    )
    seed_transaction(
        account_id,
        category_id,
        50.0,
        date=today,
        payee_id=biedronka_id,
        description="Biedronka shop 2",
    )

    page.goto(f"{base_url}/reports/top-merchants")
    expect(page.get_by_text("Top Merchants", exact=True).first).to_be_visible(timeout=5000)

    table = page.locator(".q-table")
    expect(table.get_by_text("Lidl PID E2E", exact=True)).to_be_visible(timeout=5000)
    expect(table.get_by_text("Biedronka PID E2E", exact=True)).to_be_visible(timeout=5000)

    lidl_row = table.locator("tbody tr").filter(has_text="Lidl PID E2E")
    biedronka_row = table.locator("tbody tr").filter(has_text="Biedronka PID E2E")
    expect(lidl_row).to_be_visible()
    expect(biedronka_row).to_be_visible()

    lidl_index = lidl_row.evaluate("el => Array.from(el.parentElement.children).indexOf(el)")
    biedronka_index = biedronka_row.evaluate(
        "el => Array.from(el.parentElement.children).indexOf(el)"
    )
    assert lidl_index < biedronka_index, "Higher-spend payee should appear above lower-spend payee"
