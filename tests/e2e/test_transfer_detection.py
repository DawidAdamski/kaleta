"""E2E tests for Feature: mBank CSV Import — transfer detection.

Covers: KAL-CSV-004

Maps internal transfer detection between two registered accounts.
Page URL: /import (preview) and /transactions (verification)
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect

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
    page.locator(".q-select").filter(has_text=label).click()
    page.locator(".q-menu").get_by_text(option, exact=True).click()


def test_mbank_transfer_to_registered_account_detected(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-004"""
    expense_cat = "Other Expenses Transfer E2E"
    income_cat = "Other Income Transfer E2E"

    seed_account_with_external(MAIN_ACCOUNT, MAIN_EXTERNAL)
    seed_account_with_external(SAVINGS_ACCOUNT, SAVINGS_EXTERNAL)
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(MBANK_CSV))

    expect(page.get_by_text("mbank_transfer.csv")).to_be_visible(timeout=5000)
    expect(page.get_by_text("Loaded 3 rows", exact=False).first).to_be_visible(timeout=5000)

    _select_import_option(page, "Target account", _account_option(MAIN_ACCOUNT))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    preview = page.locator(".q-table")
    expect(preview.get_by_text("transfer", exact=False).first).to_be_visible(timeout=5000)
    expect(preview.get_by_text("expense", exact=False).first).to_be_visible(timeout=5000)
    expect(preview.get_by_text("income", exact=False).first).to_be_visible(timeout=5000)

    page.get_by_role("button", name="Import all").click()
    expect(page.get_by_text("Imported", exact=False).first).to_be_visible(timeout=10000)

    page.goto(f"{base_url}/transactions")

    search = page.get_by_label("Search description")
    search.click(click_count=3)
    search.fill("Jan Kowalski — Transfer E2E")

    transfer_row = page.locator(".q-table tbody tr").filter(
        has_text="Jan Kowalski — Transfer E2E"
    ).first
    expect(transfer_row).to_be_visible(timeout=5000)
    expect(transfer_row.get_by_role("cell", name="transfer", exact=True)).to_be_visible(
        timeout=5000
    )

    search.click(click_count=3)
    search.fill("Biedronka Transfer E2E")
    expense_row = page.locator(".q-table tbody tr").filter(has_text="Biedronka Transfer E2E").first
    expect(expense_row.get_by_role("cell", name="expense", exact=True)).to_be_visible(timeout=5000)

    search.click(click_count=3)
    search.fill("Salary Transfer E2E")
    income_row = page.locator(".q-table tbody tr").filter(has_text="Salary Transfer E2E").first
    expect(income_row.get_by_role("cell", name="income", exact=True)).to_be_visible(timeout=5000)
