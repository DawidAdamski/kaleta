# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: mBank CSV Import — transfer detection.

Covers: KAL-CSV-004

Maps internal transfer detection between two registered accounts.
Page URL: /import (preview) and /transactions (verification)
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.ledger import search_ledger
from tests.e2e.seed_helpers import (
    seed_account_with_external,
    seed_category,
    seed_income_category,
)

MBANK_CSV = Path(__file__).resolve().parent / "fixtures" / "mbank_transfer.csv"

MAIN_ACCOUNT = "mBank PLN Transfer E2E"
SAVINGS_ACCOUNT = "mBank Savings Transfer E2E"
MAIN_EXTERNAL = "55114020040000330278886836"
SAVINGS_EXTERNAL = "12114020040000330299991234"


def _account_option(name: str, currency: str = "PLN") -> str:
    return f"{name} ({currency})"


def _select_import_option(page: Page, label: str, option: str) -> None:
    page.keyboard.press("Escape")
    page.locator(".q-select").filter(has_text=label).click()
    page.locator(".q-menu").last.get_by_text(option, exact=True).click()


def _step(page: Page, step: int) -> None:
    """Walk the import wizard to *step* — it shows one at a time."""
    page.keyboard.press("Escape")
    page.locator(f'[data-step="{step}"]').click()
    expect(page.locator(f'[data-step-panel="{step}"]')).to_be_visible(timeout=5000)


def test_mbank_transfer_to_registered_account_detected(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-004"""
    # Leading "AAA" keeps these near the top of Quasar's virtualised select list
    # when the shared e2e DB already has many categories from earlier tests.
    expense_cat = "AAA Transfer Expense"
    income_cat = "AAA Transfer Income"

    seed_account_with_external(MAIN_ACCOUNT, MAIN_EXTERNAL)
    seed_account_with_external(SAVINGS_ACCOUNT, SAVINGS_EXTERNAL)
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(MBANK_CSV))

    expect(page.locator("[data-page-eyebrow]")).to_contain_text("mbank_transfer.csv", timeout=10000)

    _step(page, 4)
    expect(page.get_by_text("Import settings", exact=True)).to_be_visible(timeout=5000)
    _select_import_option(page, "Target account", _account_option(MAIN_ACCOUNT))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    # The preview is its own step now, and the import runs from its footer.
    _step(page, 5)
    preview = page.locator(".q-table")
    expect(preview.get_by_role("cell", name="Transfer", exact=True).first).to_be_visible(
        timeout=5000
    )
    expect(preview.get_by_role("cell", name="Expense", exact=True).first).to_be_visible(
        timeout=5000
    )
    expect(preview.get_by_role("cell", name="Income", exact=True).first).to_be_visible(timeout=5000)

    page.locator("[data-import-run]").click()
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)

    page.goto(f"{base_url}/transactions")

    search_ledger(page, "Jan Kowalski — Transfer E2E")

    transfer_row = (
        page.locator(".q-table tbody tr").filter(has_text="Jan Kowalski — Transfer E2E").first
    )
    expect(transfer_row).to_be_visible(timeout=5000)
    expect(transfer_row.get_by_role("cell", name="Transfer", exact=True)).to_be_visible(
        timeout=5000
    )

    search_ledger(page, "Biedronka Transfer E2E")
    expense_row = page.locator(".q-table tbody tr").filter(has_text="Biedronka Transfer E2E").first
    expect(expense_row.get_by_role("cell", name="Expense", exact=True)).to_be_visible(timeout=5000)

    search_ledger(page, "Salary Transfer E2E")
    income_row = page.locator(".q-table tbody tr").filter(has_text="Salary Transfer E2E").first
    expect(income_row.get_by_role("cell", name="Income", exact=True)).to_be_visible(timeout=5000)
