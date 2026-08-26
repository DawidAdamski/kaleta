# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Money Flow.

Maps scenarios from docs/bdd.md — Feature: Money Flow.
Page URL: /reports/money-flow
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    seed_account,
    seed_category,
    seed_income_category,
    seed_transaction,
)


def test_money_flow_page_loads_with_kpis(page: Page, base_url: str) -> None:
    """Covers: KAL-FLW-001, KAL-FLW-002"""
    today = datetime.date.today()
    acc = seed_account("Money Flow Checking E2E")
    salary = seed_income_category("MF Salary E2E")
    food = seed_category("MF Food E2E")
    seed_transaction(acc, salary, 5000.0, tx_type="income", date=today, description="salary")
    seed_transaction(acc, food, 1200.0, tx_type="expense", date=today, description="food")

    page.goto(f"{base_url}/reports/money-flow")

    expect(page.get_by_text("Money Flow", exact=True).first).to_be_visible(timeout=10000)
    expect(page.get_by_text("Total Income", exact=True)).to_be_visible(timeout=15000)
    expect(page.get_by_text("Total Expenses", exact=True)).to_be_visible(timeout=5000)
    # Surplus KPI appears when income > expenses (KAL-FLW-002)
    expect(page.get_by_text("Surplus", exact=True).first).to_be_visible(timeout=5000)
    period = f"{today.year}-{today.month:02d}"
    expect(page.get_by_text(f"Money flow — {period}")).to_be_visible(timeout=5000)
    expect(page.get_by_role("button", name="Export CSV")).to_be_visible(timeout=5000)
