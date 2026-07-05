# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: mBank CSV Import (generic CSV path).

Covers: KAL-CSV-001

Maps the q3-test-safety-net CSV import flow using ``test_import.csv``.
Page URL: /import
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_category, seed_income_category

IMPORT_CSV = Path(__file__).resolve().parents[2] / "test_import.csv"


def _select_import_option(page: Page, label: str, option: str) -> None:
    page.locator(".q-select").filter(has_text=label).click()
    page.locator(".q-menu").get_by_text(option, exact=True).click()


def _account_option(name: str, currency: str = "PLN") -> str:
    return f"{name} ({currency})"


def test_csv_import_with_account_mapping(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-001

    Uses the repo-root ``test_import.csv`` (generic CSV profile) with explicit
    target-account and default category mapping per q3-test-safety-net.
    """
    account_name = "Import E2E Account"
    expense_cat = "Other Expenses Import E2E"
    income_cat = "Other Income Import E2E"

    seed_account(account_name)
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)

    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))

    expect(page.get_by_text("test_import.csv")).to_be_visible(timeout=5000)
    expect(page.get_by_text("Biedronka", exact=False).first).to_be_visible(timeout=5000)

    _select_import_option(page, "Target account", _account_option(account_name))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    page.get_by_role("button", name="Import all").click()

    expect(page.get_by_text("Imported", exact=False).first).to_be_visible(timeout=10000)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=5000)

    page.goto(f"{base_url}/transactions")
    search = page.get_by_label("Search description")
    for label in ("Biedronka", "Orlen", "Wyplata"):
        search.click(click_count=3)
        search.fill(label)
        expect(page.get_by_text(label).first).to_be_visible(timeout=5000)
