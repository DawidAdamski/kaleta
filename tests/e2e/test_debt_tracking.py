# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Debt Tracking.

Page URL: /wizard/personal-loans
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_personal_loan


def _fill_number(scope: Page, label: str, value: str) -> None:
    field = scope.get_by_role("spinbutton", name=label, exact=True)
    field.click(click_count=3)
    field.fill(value)


def test_debts_panel_shows_balance_per_person(page: Page, base_url: str) -> None:
    """Covers: KAL-DBT-002

    Outstanding loans to and from counterparties appear on the debts panel with
    aggregate header totals and per-person remaining balances.
    """
    seed_personal_loan("Marek DBT E2E", 400.0, direction="outgoing")
    seed_personal_loan("Ania DBT E2E", 150.0, direction="incoming")

    page.goto(f"{base_url}/wizard/personal-loans")
    expect(page.get_by_text("Personal Loans", exact=True).first).to_be_visible(timeout=5000)

    expect(page.get_by_text("They owe you", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("You owe", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("400.00").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("150.00").first).to_be_visible(timeout=5000)

    expect(page.get_by_text("Marek DBT E2E", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Ania DBT E2E", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Remaining: 400.00 PLN", exact=True).first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Remaining: 150.00 PLN", exact=True).first).to_be_visible(timeout=5000)


def test_repayment_reduces_outstanding_balance(page: Page, base_url: str) -> None:
    """Covers: KAL-DBT-003

    Recording a repayment against an outstanding loan reduces the remaining balance.
    """
    seed_personal_loan("Marek Repay E2E", 400.0, direction="outgoing")

    page.goto(f"{base_url}/wizard/personal-loans")
    expect(page.get_by_text("Marek Repay E2E", exact=True)).to_be_visible(timeout=5000)

    loan_block = page.locator(".rounded.border").filter(has_text="Marek Repay E2E")
    expect(loan_block.get_by_text("Remaining: 400.00 PLN", exact=True).first).to_be_visible(
        timeout=5000
    )

    loan_block.locator("button").nth(1).click()

    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Record repayment", exact=True)).to_be_visible(timeout=5000)
    _fill_number(dialog, "Amount", "250")
    dialog.get_by_role("button", name="Save").click()

    expect(loan_block.get_by_text("Remaining: 150.00 PLN", exact=True).first).to_be_visible(
        timeout=5000
    )
