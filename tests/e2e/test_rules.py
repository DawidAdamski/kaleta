# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Auto-categorisation Rules.

Covers: KAL-RUL-001, KAL-RUL-002

Page URL: /rules, /import
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    get_or_seed_category,
    seed_account,
    seed_category,
    seed_income_category,
    seed_rule,
)


def _select_option(page: Page, label: str, option: str) -> None:
    page.locator(".q-select").filter(has_text=label).click()
    page.locator(".q-menu").get_by_text(option, exact=True).click()


def _account_option(name: str, currency: str = "PLN") -> str:
    return f"{name} ({currency})"


def test_create_categorisation_rule(page: Page, base_url: str) -> None:
    """Covers: KAL-RUL-001

    Given I am on the Rules page
    When I add a rule: description contains "LIDL" sets category "Groceries"
    Then the rule appears in the rules list
    """
    get_or_seed_category("Groceries")

    page.goto(f"{base_url}/rules")
    expect(page.get_by_text("Rules", exact=True).first).to_be_visible(timeout=5000)

    page.get_by_role("button", name="Add Rule").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_label("Pattern").fill("LIDL")
    dialog.locator(".q-select").filter(has_text="Category").click()
    page.locator(".q-menu").get_by_text("Groceries", exact=True).click()
    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("LIDL").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Groceries").first).to_be_visible(timeout=5000)


def test_rules_apply_during_csv_import(page: Page, base_url: str) -> None:
    """Covers: KAL-RUL-002

    Given a rule mapping "LIDL" to "Groceries"
    When I import a CSV containing a LIDL transaction
    Then the imported transaction is pre-categorised "Groceries"
    """
    account_name = "Rules Import Account"
    expense_default = "Other Expenses Rules E2E"
    income_cat = "Other Income Rules E2E"
    groceries = "Groceries"

    seed_account(account_name)
    seed_category(expense_default)
    seed_income_category(income_cat)
    groceries_id = get_or_seed_category(groceries)
    seed_rule("LIDL", groceries_id)

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "amount", "description"])
        writer.writerow(["2024-03-15", "-45.00", "LIDL Warszawa"])
        csv_path = Path(fh.name)

    try:
        page.goto(f"{base_url}/import")
        expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(
            timeout=5000
        )

        page.locator('input[type="file"]').set_input_files(str(csv_path))
        expect(page.get_by_text("LIDL Warszawa", exact=False).first).to_be_visible(timeout=5000)

        _select_option(page, "Target account", _account_option(account_name))
        _select_option(page, "Default expense category", expense_default)
        _select_option(page, "Default income category", income_cat)

        page.get_by_role("button", name="Import 1 file").click()
        expect(page.get_by_text("Imported", exact=True).first).to_be_visible(timeout=10000)

        page.goto(f"{base_url}/transactions")
        search = page.get_by_label("Search description")
        search.click(click_count=3)
        search.fill("LIDL")
        expect(page.get_by_text("LIDL Warszawa").first).to_be_visible(timeout=5000)
        row = page.locator(".q-table tbody tr").filter(has_text="LIDL Warszawa")
        expect(row.get_by_text("Groceries").first).to_be_visible(timeout=5000)
    finally:
        csv_path.unlink(missing_ok=True)
