# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for transfer detection and recognition.

Covers: KAL-CSV-004, KAL-TRF-001, KAL-TRF-002

Maps internal transfer detection between two registered accounts, manual
pairing of two ledger rows, and the transfer-pair suggestions on the
import's Confirm step.
Page URL: /import (preview, confirm) and /transactions (verification)
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.ledger import pick_open_menu_option, search_ledger
from tests.e2e.seed_helpers import (
    get_transaction,
    seed_account,
    seed_account_with_external,
    seed_category,
    seed_income_category,
    seed_transaction,
)

MBANK_CSV = Path(__file__).resolve().parent / "fixtures" / "mbank_transfer.csv"
PAIRS_CSV = Path(__file__).resolve().parent / "fixtures" / "mbank_transfer_pairs.csv"

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


def _pick_import_option(page: Page, label: str, option: str) -> None:
    """Like ``_select_import_option``, but scrolls a long virtualised list.

    By the time the whole suite has run, the shared DB holds dozens of
    accounts, and the one this test seeded is not rendered until scrolled to.
    """
    page.keyboard.press("Escape")
    page.locator(".q-select").filter(has_text=label).click()
    pick_open_menu_option(page, option)


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

    expect(page.locator("[data-page-eyebrow]")).to_contain_text("mbank_transfer.csv", timeout=5000)

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
    # The heading renders for a failed run too, so the claim is the file's
    # own line in the summary.
    expect(page.locator('[data-step-panel="6"]')).to_contain_text(
        re.compile(r"\b3 imported"), timeout=10000
    )

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


def test_manually_pair_two_rows_as_a_transfer(page: Page, base_url: str) -> None:
    """Covers: KAL-TRF-001"""
    token = "TRF001 E2E"
    mbank = seed_account("mBank TRF-001 E2E")
    pko = seed_account("PKO BP TRF-001 E2E")
    expense_id = seed_transaction(
        mbank,
        seed_category("TRF-001 Expense E2E"),
        500.00,
        date=datetime.date(2026, 7, 1),
        description=f"Out {token}",
    )
    income_id = seed_transaction(
        pko,
        seed_income_category("TRF-001 Income E2E"),
        500.00,
        tx_type="income",
        date=datetime.date(2026, 7, 1),
        description=f"In {token}",
    )

    page.goto(f"{base_url}/transactions")
    search_ledger(page, token)
    rows = page.locator(".q-table tbody tr").filter(has_text=token)
    expect(rows).to_have_count(2, timeout=10000)

    bar_button = page.locator("[data-mark-transfer]")
    rows.nth(0).locator(".q-checkbox").click()
    expect(page.get_by_text("1 selected", exact=True)).to_be_visible(timeout=10000)
    # One row is not a transfer: the action is on the bar but off.
    expect(bar_button).to_be_disabled()
    rows.nth(1).locator(".q-checkbox").click()
    expect(page.get_by_text("2 selected", exact=True)).to_be_visible(timeout=10000)
    expect(bar_button).to_be_enabled()
    bar_button.click()

    expect(page.get_by_text("The two rows are now one transfer.")).to_be_visible(timeout=10000)
    for row_text in (f"Out {token}", f"In {token}"):
        row = page.locator(".q-table tbody tr").filter(has_text=row_text).first
        expect(row.get_by_role("cell", name="Transfer", exact=True)).to_be_visible(timeout=10000)

    out_leg = get_transaction(expense_id)
    in_leg = get_transaction(income_id)
    assert out_leg["type"] == "transfer"
    assert in_leg["type"] == "transfer"
    assert out_leg["account_id"] == mbank
    assert in_leg["account_id"] == pko
    assert out_leg["linked_transaction_id"] == income_id
    assert in_leg["linked_transaction_id"] == expense_id


def test_import_suggests_transfer_pairs_to_accept_or_dismiss(page: Page, base_url: str) -> None:
    """Covers: KAL-TRF-002"""
    mbank_name = "mBank TRF-002 E2E"
    pko_name = "PKO BP TRF-002 E2E"
    expense_cat = "AAA TRF-002 Expense"
    income_cat = "AAA TRF-002 Income"
    mbank = seed_account(mbank_name)
    pko = seed_account(pko_name)
    seed_category(expense_cat)
    income_cat_id = seed_income_category(income_cat)
    # The other legs are already on the PKO account, within 2 days of the file's rows.
    savings_in = seed_transaction(
        pko,
        income_cat_id,
        517.23,
        tx_type="income",
        date=datetime.date(2019, 3, 13),
        description="Z mBanku TRF E2E",
    )
    shop_in = seed_transaction(
        pko,
        income_cat_id,
        123.45,
        tx_type="income",
        date=datetime.date(2019, 3, 15),
        description="Zwrot TRF E2E",
    )

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(PAIRS_CSV))
    expect(page.locator("[data-page-eyebrow]")).to_contain_text(
        "mbank_transfer_pairs.csv", timeout=5000
    )
    _step(page, 4)
    _pick_import_option(page, "Target account", _account_option(mbank_name))
    _pick_import_option(page, "Default expense category", expense_cat)
    _pick_import_option(page, "Default income category", income_cat)
    _step(page, 5)
    page.locator("[data-import-run]").click()

    confirm = page.locator('[data-step-panel="6"]')
    expect(confirm).to_contain_text(re.compile(r"\b2 imported"), timeout=10000)
    section = confirm.locator("[data-transfer-section]")
    expect(section).to_be_visible(timeout=10000)
    pairs = section.locator("[data-transfer-pair]").filter(has_text=f"{mbank_name} → {pko_name}")
    expect(pairs).to_have_count(2, timeout=10000)

    savings_pair = pairs.filter(has_text="517.23")
    savings_pair.locator("[data-transfer-accept]").click()
    expect(page.get_by_text("Linked as one transfer.")).to_be_visible(timeout=10000)
    expect(pairs).to_have_count(1, timeout=10000)

    pairs.filter(has_text="123.45").locator("[data-transfer-dismiss]").click()
    expect(page.get_by_text("This pair will not be suggested again.")).to_be_visible(timeout=10000)
    expect(pairs).to_have_count(0, timeout=10000)

    accepted = get_transaction(savings_in)
    assert accepted["type"] == "transfer"
    assert accepted["linked_transaction_id"] is not None
    dismissed = get_transaction(shop_in)
    assert dismissed["type"] == "income"
    assert dismissed["linked_transaction_id"] is None
    # The imported mBank row is the outgoing leg it was linked to.
    out_leg = get_transaction(accepted["linked_transaction_id"])
    assert out_leg["type"] == "transfer"
    assert out_leg["account_id"] == mbank
    assert out_leg["linked_transaction_id"] == savings_in
