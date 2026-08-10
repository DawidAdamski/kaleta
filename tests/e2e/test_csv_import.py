# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: mBank CSV Import (generic CSV path).

Covers: KAL-CSV-001, KAL-CSV-010, KAL-CSV-011

Maps the q3-test-safety-net CSV import flow using ``test_import.csv``.
Page URL: /import
"""

from __future__ import annotations

import datetime
from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    seed_account,
    seed_category,
    seed_income_category,
    seed_transaction,
)

IMPORT_CSV = Path(__file__).resolve().parents[2] / "test_import.csv"


def _select_import_option(page: Page, label: str, option: str) -> None:
    page.locator(".q-select").filter(has_text=label).click()
    page.locator(".q-menu").get_by_text(option, exact=True).click()


def _account_option(name: str, currency: str = "PLN") -> str:
    return f"{name} ({currency})"


def _configure_and_upload(
    page: Page,
    base_url: str,
    *,
    account: str,
    expense: str,
    income: str,
) -> None:
    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)

    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))

    expect(page.get_by_text("test_import.csv")).to_be_visible(timeout=5000)
    expect(page.get_by_text("Biedronka", exact=False).first).to_be_visible(timeout=5000)

    _select_import_option(page, "Target account", _account_option(account))
    _select_import_option(page, "Default expense category", expense)
    _select_import_option(page, "Default income category", income)


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

    _configure_and_upload(
        page, base_url, account=account_name, expense=expense_cat, income=income_cat
    )

    page.get_by_role("button", name="Import 1 file").click()

    expect(page.get_by_text("Imported", exact=False).first).to_be_visible(timeout=10000)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=5000)

    page.goto(f"{base_url}/transactions")
    search = page.get_by_label("Search description")
    for label in ("Biedronka", "Orlen", "Wyplata"):
        search.click(click_count=3)
        search.fill(label)
        expect(page.get_by_text(label).first).to_be_visible(timeout=5000)


def test_start_new_import_without_reload(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-010

    After a completed import, Start new import clears the queue so a second
    file can be imported without reloading the page.
    """
    account_name = "Import Reset Account"
    expense_cat = "Other Expenses Import Reset"
    income_cat = "Other Income Import Reset"

    seed_account(account_name)
    seed_category(expense_cat)
    seed_income_category(income_cat)

    _configure_and_upload(
        page, base_url, account=account_name, expense=expense_cat, income=income_cat
    )
    page.get_by_role("button", name="Import 1 file").click()
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_role("button", name="Start new import")).to_be_visible()

    page.get_by_role("button", name="Start new import").click()
    expect(page.get_by_text("Import summary", exact=True)).not_to_be_visible(timeout=5000)
    expect(
        page.get_by_text("Drop one or more files above to build the import queue.")
    ).to_be_visible(timeout=5000)

    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))
    expect(page.get_by_text("test_import.csv").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Ready", exact=True).first).to_be_visible(timeout=5000)
    # Settings inherited from the previous session — categories may be pre-filled.
    # Re-select account if needed (generic profile does not copy account).
    account_sel = page.locator(".q-select").filter(has_text="Target account")
    if "Import Reset Account" not in (account_sel.inner_text() or ""):
        _select_import_option(page, "Target account", _account_option(account_name))
    expense_sel = page.locator(".q-select").filter(has_text="Default expense category")
    if expense_cat not in (expense_sel.inner_text() or ""):
        _select_import_option(page, "Default expense category", expense_cat)
    income_sel = page.locator(".q-select").filter(has_text="Default income category")
    if income_cat not in (income_sel.inner_text() or ""):
        _select_import_option(page, "Default income category", income_cat)

    page.get_by_role("button", name="Import 1 file").click()
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_role("button", name="Start new import")).to_be_visible()


def test_skipped_duplicates_listed_with_help(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-011

    Skip-duplicates help explains the matching rule; skipped rows appear in an
    expandable summary list with date, amount and description.
    """
    account_name = "Import Dedupe Account"
    expense_cat = "Other Expenses Import Dedupe"
    income_cat = "Other Income Import Dedupe"

    account_id = seed_account(account_name)
    expense_id = seed_category(expense_cat)
    seed_income_category(income_cat)
    # Match the first row of test_import.csv exactly.
    seed_transaction(
        account_id,
        expense_id,
        50.00,
        tx_type="expense",
        date=datetime.date(2024, 1, 15),
        description="Biedronka",
    )

    _configure_and_upload(
        page, base_url, account=account_name, expense=expense_cat, income=income_cat
    )

    help_icon = page.locator(".q-icon").filter(has_text="help_outline")
    # NiceGUI/Quasar material icons render as text content "help_outline".
    expect(page.get_by_text("Skip existing transactions (duplicates)")).to_be_visible()
    help_icon.first.hover()
    expect(
        page.get_by_text(
            "A row is skipped when the same account, date, amount and description already exist."
        )
    ).to_be_visible(timeout=5000)

    page.get_by_role("button", name="Import 1 file").click()
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_text("Skipped 1 duplicates", exact=True)).to_be_visible(timeout=5000)

    page.get_by_text("Skipped 1 duplicates", exact=True).click()
    expect(page.get_by_text("2024-01-15 · 50.00 · Biedronka", exact=True)).to_be_visible(
        timeout=5000
    )
