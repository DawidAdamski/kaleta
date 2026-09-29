# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Debt Tracking.

Page URL: /wizard/personal-loans
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.ledger import pick_open_menu_option
from tests.e2e.seed_helpers import (
    seed_account,
    seed_category,
    seed_personal_loan,
    seed_transaction,
)


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
    expect(page.get_by_role("main").get_by_text("Personal Loans", exact=True).first).to_be_visible(
        timeout=5000
    )

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


def test_lending_linked_to_yesterdays_transfer(page: Page, base_url: str) -> None:
    """Covers: KAL-DBT-001

    The add-loan dialog links an existing transaction (yesterday's transfer);
    picking it fills the principal, and the loan shows the full balance.
    """
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    acc_id = seed_account("Konto DBT001 E2E")
    cat_id = seed_category("Przelewy DBT001 E2E")
    tx_id = seed_transaction(
        acc_id, cat_id, 400.0, date=yesterday, description="Przelew dla Marka DBT001"
    )

    page.goto(f"{base_url}/wizard/personal-loans")
    page.get_by_role("button", name="New loan").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Counterparty").fill("Marek DBT001 E2E")
    dialog.get_by_label("Linked transaction").click()
    pick_open_menu_option(
        page,
        f"{yesterday:%d.%m.%Y} · 400.00 · Przelew dla Marka DBT001 · Konto DBT001 E2E",
    )
    expect(dialog.get_by_role("spinbutton", name="Amount", exact=True)).to_have_value(
        "400.00", timeout=5000
    )
    dialog.get_by_role("button", name="Save").click()

    loan_block = page.locator(".rounded.border").filter(has_text="Marek DBT001 E2E")
    expect(loan_block.get_by_text("Remaining: 400.00 PLN", exact=True).first).to_be_visible(
        timeout=5000
    )
    expect(loan_block.get_by_text(f"Transaction #{tx_id}")).to_be_visible(timeout=5000)


def test_lent_money_is_not_an_expense(page: Page, base_url: str) -> None:
    """Covers: KAL-DBT-004

    A 400.00 transfer recorded as a loan to Marek appears under Loans in the
    monthly income statement, not among the expense categories.
    """
    # Same month last year: the suite shares one database, and the KAL-DBT-001
    # test links its own 400.00 transfer in the current month.
    today = datetime.date.today()
    month_start = datetime.date(today.year - 1, today.month, 1)
    acc_id = seed_account("Konto DBT004 E2E")
    cat_id = seed_category("Przelew Marek DBT004 E2E")
    tx_id = seed_transaction(
        acc_id, cat_id, 400.0, date=month_start, description="Pożyczka dla Marka DBT004"
    )
    seed_personal_loan("Marek DBT004 E2E", 400.0, opened_at=month_start, transaction_id=tx_id)

    page.goto(f"{base_url}/reports/income-statement")
    page.get_by_role("combobox", name="Year").click()
    pick_open_menu_option(page, str(month_start.year))

    loans_card = page.locator(".q-card").filter(has=page.get_by_text("Loans", exact=True))
    expect(loans_card.get_by_role("row", name="Lent or repaid 400.00 zł")).to_be_visible(
        timeout=10000
    )
    expect(page.get_by_text("Przelew Marek DBT004 E2E", exact=True)).to_have_count(0)
