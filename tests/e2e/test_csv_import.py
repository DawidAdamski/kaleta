# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: mBank CSV Import (generic CSV path).

Covers: KAL-CSV-001, KAL-CSV-005, KAL-CSV-006, KAL-CSV-007, KAL-CSV-008,
KAL-CSV-009, KAL-CSV-010, KAL-CSV-011, KAL-CSV-013, KAL-CSV-014, KAL-CSV-015,
KAL-CSV-017, KAL-CSV-018

Maps the q3-test-safety-net CSV import flow using ``test_import.csv``.
Page URL: /import
"""

from __future__ import annotations

import datetime
from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    list_import_rules,
    seed_account,
    seed_category,
    seed_import_rule,
    seed_income_category,
    seed_transaction,
    update_import_rule,
)

IMPORT_CSV = Path(__file__).resolve().parents[2] / "test_import.csv"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "import"
UNRECOGNISED_CSV = FIXTURES / "unrecognised_headers.csv"
MBANK_OCT = FIXTURES / "mbank-2025-10.csv"
MBANK_NOV = FIXTURES / "mbank-2025-11.csv"
MBANK_DEC = FIXTURES / "mbank-2025-12.csv"
BULK_MBANK = FIXTURES / "bulk-mbank-2025-10.csv"
PKO_OCT = FIXTURES / "pko-2025-10.csv"
OTHER_A = FIXTURES / "other-a.csv"
OTHER_B = FIXTURES / "other-b.csv"
OTHER_C = FIXTURES / "other-c.csv"


def _select_import_option(page: Page, label: str, option: str) -> None:
    page.keyboard.press("Escape")
    page.locator(".q-select").filter(has_text=label).click()
    page.locator(".q-menu").last.get_by_text(option, exact=True).click()


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

    expect(page.get_by_text("test_import.csv").first).to_be_visible(timeout=5000)
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

    expect(page.get_by_text("Imported", exact=True).first).to_be_visible(timeout=10000)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=5000)

    page.goto(f"{base_url}/transactions")
    search = page.get_by_label("Search description")
    for label in ("Biedronka", "Orlen", "Wyplata"):
        search.click(click_count=3)
        search.fill(label)
        expect(page.get_by_text(label).first).to_be_visible(timeout=5000)


def test_map_unrecognised_csv_and_import(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-005

    Upload a CSV whose headers the alias parser does not know, map columns,
    then import successfully.
    """
    account_name = "Revolut PLN"
    expense_cat = "Other Expenses Mapping E2E"
    income_cat = "Other Income Mapping E2E"

    seed_account(account_name)
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)
    expect(
        page.get_by_text("Generic CSV — any CSV; you map the columns yourself in the next step.")
    ).to_be_visible()

    page.locator('input[type="file"]').set_input_files(str(UNRECOGNISED_CSV))
    expect(page.get_by_text("unrecognised_headers.csv")).to_be_visible(timeout=5000)
    expect(page.get_by_text("Column mapping", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Needs mapping", exact=True).first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Date column is required.")).to_be_visible()

    _select_import_option(page, "Date column", "1: Txn Day")
    _select_import_option(page, "Amount column", "2: Sum")
    _select_import_option(page, "Description column", "3: Note")

    expect(page.get_by_text("Ready", exact=True).first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Coffee Shop", exact=False).first).to_be_visible(timeout=5000)

    _select_import_option(page, "Target account", _account_option(account_name))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    page.get_by_role("button", name="Import 1 file").click()
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_text("Imported", exact=True).first).to_be_visible(timeout=5000)

    page.goto(f"{base_url}/transactions")
    search = page.get_by_label("Search description")
    search.fill("Coffee Shop")
    expect(page.get_by_text("Coffee Shop").first).to_be_visible(timeout=5000)


def test_mapping_prefills_from_alias_detection(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-006

    Known-alias CSV pre-fills mapping dropdowns and shows a preview without
    manual remapping.
    """
    seed_account("Alias Prefill Account")
    seed_category("Other Expenses Prefill")
    seed_income_category("Other Income Prefill")

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))

    expect(page.get_by_text("test_import.csv").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Column mapping", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Ready", exact=True).first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Biedronka", exact=False).first).to_be_visible(timeout=5000)

    date_sel = page.locator(".q-select").filter(has_text="Date column")
    expect(date_sel).to_contain_text("1: date")
    amount_sel = page.locator(".q-select").filter(has_text="Amount column")
    expect(amount_sel).to_contain_text("2: amount")
    desc_sel = page.locator(".q-select").filter(has_text="Description column")
    expect(desc_sel).to_contain_text("3: description")


def test_invalid_mapping_blocks_import(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-007

    Clearing a required mapping shows an inline error and keeps Import disabled.
    """
    seed_account("Mapping Block Account")
    seed_category("Other Expenses Block")
    seed_income_category("Other Income Block")

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))
    expect(page.get_by_text("Ready", exact=True).first).to_be_visible(timeout=5000)

    _select_import_option(page, "Date column", "— not mapped —")

    expect(page.get_by_text("Date column is required.")).to_be_visible(timeout=5000)
    expect(page.get_by_text("Needs mapping", exact=True).first).to_be_visible(timeout=5000)
    import_btn = page.get_by_role("button", name="Import", exact=True)
    expect(import_btn).to_be_disabled()


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


def test_multi_file_queue_keeps_per_file_account(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-013"""
    mbank = "mBank PLN Memory"
    pko = "PKO PLN Memory"
    seed_account(mbank)
    seed_account(pko)
    seed_category("Other Expenses Multi")
    seed_income_category("Other Income Multi")

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files([str(MBANK_OCT), str(PKO_OCT)])
    expect(page.get_by_text("mbank-2025-10.csv").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("pko-2025-10.csv").first).to_be_visible(timeout=5000)

    page.get_by_text("mbank-2025-10.csv").first.click()
    page.wait_for_timeout(400)
    _select_import_option(page, "Target account", _account_option(mbank))
    expect(page.get_by_text(_account_option(mbank)).first).to_be_visible(timeout=5000)

    page.get_by_text("pko-2025-10.csv").first.click()
    page.wait_for_timeout(400)
    _select_import_option(page, "Target account", _account_option(pko))
    expect(page.get_by_text(_account_option(pko)).first).to_be_visible(timeout=5000)

    # Both per-file account chips remain visible in the queue after switching.
    expect(page.get_by_text(_account_option(mbank)).first).to_be_visible()
    expect(page.get_by_text(_account_option(pko)).first).to_be_visible()


def test_remember_mapping_and_auto_apply_rule(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-014, KAL-CSV-015"""
    account_name = "mBank PLN Remember"
    expense_cat = "Other Expenses Remember"
    income_cat = "Other Income Remember"
    seed_account(account_name)
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(MBANK_OCT))
    expect(page.get_by_text("mbank-2025-10.csv").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Ready", exact=True).first).to_be_visible(timeout=5000)

    _select_import_option(page, "Target account", _account_option(account_name))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)
    expect(page.get_by_text("Remember this mapping")).to_be_visible()
    pattern = page.get_by_label("Filename pattern")
    expect(pattern).to_have_value("mbank-*.csv")

    page.get_by_role("button", name="Import 1 file").click()
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)

    rules = list_import_rules()
    assert any(r["filename_pattern"] == "mbank-*.csv" for r in rules)

    page.get_by_role("button", name="Start new import").click()
    page.locator('input[type="file"]').set_input_files(str(MBANK_NOV))
    expect(page.get_by_text("mbank-2025-11.csv").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Rule: mbank-*.csv").first).to_be_visible(timeout=5000)
    expect(page.locator(".q-select").filter(has_text="Target account")).to_contain_text(
        account_name
    )


def test_disabled_import_rule_stops_matching(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-017"""
    account_name = "mBank PLN Disable"
    account_id = seed_account(account_name)
    seed_category("Other Expenses Disable")
    seed_income_category("Other Income Disable")
    rule_id = seed_import_rule("disable-mbank-*.csv", account_id)

    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="Import").click()
    expect(page.get_by_text("Saved import rules")).to_be_visible(timeout=5000)
    expect(page.get_by_role("cell", name="disable-mbank-*.csv").first).to_be_visible()

    update_import_rule(rule_id, is_active=False)

    # Seed an active rule with the real pattern used by uploads, then disable it.
    active_id = seed_import_rule("mbank-*.csv", account_id)
    update_import_rule(active_id, is_active=False)

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(MBANK_DEC))
    expect(page.get_by_text("mbank-2025-12.csv").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Rule: mbank-*.csv")).not_to_be_visible(timeout=3000)

    page.goto(f"{base_url}/settings")
    page.get_by_role("tab", name="Import").click()
    expect(page.get_by_role("cell", name="mbank-*.csv").first).to_be_visible()


def test_bulk_default_skips_matched_rule(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-018"""
    mbank = "mBank PLN Bulk"
    cash = "Cash Bulk"
    mbank_id = seed_account(mbank)
    seed_account(cash)
    seed_category("Other Expenses Bulk")
    seed_income_category("Other Income Bulk")
    seed_import_rule("bulk-mbank-*.csv", mbank_id)

    page.goto(f"{base_url}/import")
    _select_import_option(page, "Default account for this batch", _account_option(cash))
    page.locator('input[type="file"]').set_input_files(
        [str(OTHER_A), str(OTHER_B), str(OTHER_C), str(BULK_MBANK)]
    )

    expect(page.get_by_text("other-a.csv").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("bulk-mbank-2025-10.csv").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Rule: bulk-mbank-*.csv").first).to_be_visible(timeout=5000)
    # Unmatched files keep the bulk default; the matched file keeps the rule account.
    expect(page.get_by_text(_account_option(cash)).first).to_be_visible()
    expect(page.get_by_text(_account_option(mbank)).first).to_be_visible()


def test_coverage_panel_after_import(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-008"""
    account = "Coverage mBank PLN"
    empty = "Coverage Empty"
    expense = "Other Expenses Coverage"
    income = "Other Income Coverage"
    seed_account(account)
    seed_account(empty)
    seed_category(expense)
    seed_income_category(income)

    _configure_and_upload(page, base_url, account=account, expense=expense, income=income)
    page.get_by_role("button", name="Import 1 file").click()
    expect(page.get_by_text("Import summary")).to_be_visible(timeout=10000)

    expect(page.get_by_text("Account coverage")).to_be_visible()
    expect(page.get_by_text(account).first).to_be_visible()
    expect(page.get_by_text("test_import.csv").first).to_be_visible()
    expect(page.get_by_text(empty).first).to_be_visible()
    expect(page.get_by_text("File history")).to_be_visible()


def test_accounts_page_last_activity(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-009"""
    loaded = "Activity Loaded"
    empty = "Activity Empty"
    expense = "Activity Expense"
    account_id = seed_account(loaded)
    seed_account(empty)
    expense_id = seed_category(expense)
    seed_transaction(
        account_id,
        expense_id,
        12.34,
        date=datetime.date(2024, 6, 15),
        description="Seeded activity",
    )

    page.goto(f"{base_url}/accounts")
    expect(page.get_by_text("Accounts", exact=True).first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Last activity").first).to_be_visible()
    expect(page.get_by_text(loaded).first).to_be_visible()
    expect(page.get_by_text("2024-06-15").first).to_be_visible()
    expect(page.get_by_text(empty).first).to_be_visible()
