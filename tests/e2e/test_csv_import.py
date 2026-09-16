# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: mBank CSV Import (generic CSV path).

Covers: KAL-CSV-001, KAL-CSV-005, KAL-CSV-006, KAL-CSV-007, KAL-CSV-008,
KAL-CSV-009, KAL-CSV-010, KAL-CSV-011, KAL-CSV-013, KAL-CSV-014, KAL-CSV-015,
KAL-CSV-017, KAL-CSV-018, KAL-CSV-019, KAL-CSV-020, KAL-CSV-021, KAL-CSV-022,
KAL-CSV-023, KAL-CSV-024, KAL-CSV-025, KAL-CSV-026,
KAL-CSV-027, KAL-CSV-028, KAL-CSV-029

Maps the q3-test-safety-net CSV import flow using ``test_import.csv``.
Page URL: /import

Since `restyle-import-wizard` the page shows one step at a time, so every
test here walks it: upload, then the step whose card holds the thing being
asserted. ``_step`` is that walk. What each test claims is unchanged — the
route through the page is.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from playwright.sync_api import FilePayload, Locator, Page, expect

from tests.e2e.ledger import search_ledger
from tests.e2e.seed_helpers import (
    count_transactions,
    delete_account,
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
WISE_JPY = FIXTURES / "wise" / "jpy-travel-sample.csv"
WISE_JPY_QIF = FIXTURES / "wise" / "jpy-travel-sample.qif"
# Wise names every statement download ``statement_<id>_<CCY>_<from>_<to>.<ext>``
# and the QIF's currency lives nowhere else, so tests that care about the
# currency upload the fixture under that name. The account-id segment is
# anonymized here as it is in the fixtures — it identifies a real wallet.
WISE_QIF_DOWNLOAD_NAME = "statement_12345678_JPY_2026-04-01_2026-06-30.qif"
AUTORESET_SECOND = FIXTURES / "autoreset-second.csv"
AUTORESET_FAILING = FIXTURES / "autoreset-failing.csv"

# The six steps, as the page numbers them.
STEP_FORMAT = 1
STEP_UPLOAD = 2
STEP_MAPPING = 3
STEP_SETTINGS = 4
STEP_PREVIEW = 5
STEP_CONFIRM = 6


def _upload_as(path: Path, name: str) -> FilePayload:
    """Feed *path*'s bytes to the upload widget under a different *name*."""
    return {
        "name": name,
        "mimeType": "application/octet-stream",
        "buffer": path.read_bytes(),
    }


def _select_import_option(page: Page, label: str, option: str) -> None:
    page.keyboard.press("Escape")
    page.locator(".q-select").filter(has_text=label).click()
    page.locator(".q-menu").last.get_by_text(option, exact=True).click()


def _account_option(name: str, currency: str = "PLN") -> str:
    return f"{name} ({currency})"


def _panel(page: Page, step: int) -> Locator:
    return page.locator(f'[data-step-panel="{step}"]')


def _step(page: Page, step: int) -> None:
    """Walk to *step* by clicking its node on the progress line.

    Only nodes the work has reached are clickable, so the class assertion
    doubles as one that the file really did get that far.
    """
    page.keyboard.press("Escape")
    node = page.locator(f'[data-step="{step}"]')
    expect(node).to_have_class(re.compile(r"cursor-pointer"), timeout=5000)
    node.click()
    expect(_panel(page, step)).to_be_visible(timeout=5000)


def _continue(page: Page) -> None:
    button = page.locator("[data-continue]")
    expect(button).to_be_enabled(timeout=5000)
    button.click()


def _blocked_reason(page: Page) -> Locator:
    return page.locator("[data-blocked-reason]")


def _wait_for_queue(page: Page, count: int) -> None:
    """Every file of a multi-file drop has joined the queue."""
    expect(page.locator("[data-queue-row]")).to_have_count(count, timeout=10000)


def _wait_for_file(page: Page, filename: str) -> None:
    """The header eyebrow names the file the wizard is now about."""
    expect(page.locator("[data-page-eyebrow]")).to_contain_text(filename, timeout=10000)


def _run_import(page: Page) -> None:
    """Press the import button, which lives in the Preview footer."""
    run = page.locator("[data-import-run]")
    expect(run).to_be_enabled(timeout=5000)
    run.click()


def _import_now(page: Page) -> None:
    _step(page, STEP_PREVIEW)
    _run_import(page)


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

    _wait_for_file(page, "test_import.csv")
    _step(page, STEP_SETTINGS)
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

    _step(page, STEP_PREVIEW)
    expect(_panel(page, STEP_PREVIEW).get_by_text("Biedronka", exact=False).first).to_be_visible(
        timeout=5000
    )
    _run_import(page)

    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=5000)

    page.goto(f"{base_url}/transactions")
    for label in ("Biedronka", "Orlen", "Wyplata"):
        search_ledger(page, label)
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
    _step(page, STEP_FORMAT)
    expect(
        page.get_by_text("Generic CSV — any CSV; you map the columns yourself in the next step.")
    ).to_be_visible()

    _step(page, STEP_UPLOAD)
    page.locator('input[type="file"]').set_input_files(str(UNRECOGNISED_CSV))

    # Unrecognised headers park the file on the mapping step, and the page
    # goes there with it — one card, and the reason Continue will not leave.
    _wait_for_file(page, "unrecognised_headers.csv")
    expect(_panel(page, STEP_MAPPING)).to_be_visible(timeout=10000)
    expect(page.get_by_text("Column mapping", exact=True)).to_be_visible()
    expect(page.get_by_text("Date column is required.")).to_be_visible()
    expect(_blocked_reason(page)).to_have_text("Map the required columns to continue.")
    expect(page.locator("[data-continue]")).to_be_disabled()

    _select_import_option(page, "Date column", "1: Txn Day")
    _select_import_option(page, "Amount column", "2: Sum")
    _select_import_option(page, "Description column", "3: Note")

    # Mapped: the step behind is finished, so Continue stops refusing.
    expect(page.locator("[data-continue]")).to_be_enabled(timeout=5000)
    _continue(page)

    _select_import_option(page, "Target account", _account_option(account_name))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    _step(page, STEP_PREVIEW)
    expect(_panel(page, STEP_PREVIEW).get_by_text("Coffee Shop", exact=False).first).to_be_visible(
        timeout=5000
    )
    _run_import(page)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(_panel(page, STEP_CONFIRM).get_by_text("imported", exact=False).first).to_be_visible(
        timeout=5000
    )

    page.goto(f"{base_url}/transactions")
    search_ledger(page, "Coffee Shop")
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

    # Known aliases mean nothing to map by hand, so the page walks past the
    # mapping step; it is still there, pre-filled, for whoever looks.
    _wait_for_file(page, "test_import.csv")
    _step(page, STEP_MAPPING)
    expect(page.get_by_text("Column mapping", exact=True)).to_be_visible()
    expect(_panel(page, STEP_MAPPING).get_by_text("Biedronka", exact=False).first).to_be_visible(
        timeout=5000
    )

    date_sel = page.locator(".q-select").filter(has_text="Date column")
    expect(date_sel).to_contain_text("1: date")
    amount_sel = page.locator(".q-select").filter(has_text="Amount column")
    expect(amount_sel).to_contain_text("2: amount")
    desc_sel = page.locator(".q-select").filter(has_text="Description column")
    expect(desc_sel).to_contain_text("3: description")


def test_invalid_mapping_blocks_import(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-007

    Clearing a required mapping shows an inline error and keeps Continue
    disabled — the import button is a step further on, and unreachable.
    """
    seed_account("Mapping Block Account")
    seed_category("Other Expenses Block")
    seed_income_category("Other Income Block")

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))
    _wait_for_file(page, "test_import.csv")

    _step(page, STEP_MAPPING)
    _select_import_option(page, "Date column", "— not mapped —")

    # The work fell back to this step, so there is nothing in front of the
    # reader to continue to — and the refusal says which column it wants.
    expect(page.get_by_text("Date column is required.")).to_be_visible(timeout=5000)
    expect(_blocked_reason(page)).to_have_text("Map the required columns to continue.")
    expect(page.locator("[data-continue]")).to_be_disabled()
    expect(page.locator("[data-import-run]")).to_have_count(0)


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
    _import_now(page)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_role("button", name="Start new import")).to_be_visible()

    page.get_by_role("button", name="Start new import").click()
    # An empty queue can only be on the upload step, and the summary went
    # with the run it summarised.
    expect(_panel(page, STEP_UPLOAD)).to_be_visible(timeout=5000)
    expect(page.get_by_text("Import summary", exact=True)).not_to_be_visible()
    expect(
        page.get_by_text("Drop one or more files above to build the import queue.")
    ).to_be_visible(timeout=5000)

    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))
    _wait_for_file(page, "test_import.csv")
    _step(page, STEP_SETTINGS)
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

    _import_now(page)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_role("button", name="Start new import")).to_be_visible()


def test_upload_after_completed_run_starts_fresh_queue(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-020

    Dropping a file after a completed run clears the finished queue instead of
    leaving stale done-rows next to the new file.
    """
    account_name = "Import Autoreset Account"
    expense_cat = "Other Expenses Import Autoreset"
    income_cat = "Other Income Import Autoreset"

    account_id = seed_account(account_name)
    seed_category(expense_cat)
    seed_income_category(income_cat)

    _configure_and_upload(
        page, base_url, account=account_name, expense=expense_cat, income=income_cat
    )
    _import_now(page)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    assert count_transactions(account_id) == 3

    # Drop the next file without clicking "Start new import".
    page.locator('input[type="file"]').set_input_files(str(AUTORESET_SECOND))
    _wait_for_file(page, "autoreset-second.csv")

    _step(page, STEP_UPLOAD)
    queue_card = page.locator(".q-card").filter(has=page.get_by_text("Files to import", exact=True))
    expect(queue_card.get_by_text("autoreset-second.csv").first).to_be_visible(timeout=5000)
    expect(queue_card.get_by_text("test_import.csv")).to_have_count(0)
    expect(page.get_by_text("Import summary", exact=True)).not_to_be_visible()

    # The generic profile inherits categories but never the account. Re-picking
    # all three is idempotent, so set them outright rather than inferring what
    # carried over from the rendered select labels.
    _step(page, STEP_SETTINGS)
    _select_import_option(page, "Target account", _account_option(account_name))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    _step(page, STEP_PREVIEW)
    expect(page.locator("[data-import-run]")).to_contain_text("Import 1 file")
    _run_import(page)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)

    # Exactly the second file's two rows were added — the first file did not
    # ride along a second time.
    assert count_transactions(account_id) == 5

    # Dropping several files at once onto the finished queue keeps all of them:
    # the fan-out of one handler per file must reset once, not once per file.
    page.locator('input[type="file"]').set_input_files([str(MBANK_OCT), str(PKO_OCT)])
    _wait_for_queue(page, 2)
    _step(page, STEP_UPLOAD)
    expect(queue_card.get_by_text("mbank-2025-10.csv").first).to_be_visible(timeout=5000)
    expect(queue_card.get_by_text("pko-2025-10.csv").first).to_be_visible(timeout=5000)
    expect(queue_card.get_by_text("autoreset-second.csv")).to_have_count(0)
    # Both files are live in the queue, which is what the steps that act on
    # one file say for themselves: "File 1 of 2".
    _step(page, STEP_SETTINGS)
    expect(page.locator("[data-file-switcher]")).to_contain_text("of 2", timeout=5000)


def test_upload_after_failed_run_clears_and_warns(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-021

    A failed file is terminal, so it is cleared with the rest of the run — but
    the user is told, so the failure cannot pass for a silent success.
    """
    account_name = "Import Failure Account"
    expense_cat = "Other Expenses Import Failure"
    income_cat = "Other Income Import Failure"
    account_id = seed_account(account_name)
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)

    page.locator('input[type="file"]').set_input_files(str(AUTORESET_FAILING))
    _wait_for_file(page, "autoreset-failing.csv")
    _step(page, STEP_SETTINGS)
    _select_import_option(page, "Target account", _account_option(account_name))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    # The account goes away between choosing it and importing into it, which
    # is the only way left to reach the import's own failure branch: the
    # wizard refuses every readiness problem a step earlier. The rows cannot
    # be written, so the file fails where it used to fail — during the run.
    _step(page, STEP_PREVIEW)
    delete_account(account_id)
    _run_import(page)

    # The run is over, so its summary is the step — a failed file's own
    # status would put the reader back on Upload, with the report of
    # everything that did happen on a step nobody could reach.
    expect(_panel(page, STEP_CONFIRM)).to_be_visible(timeout=10000)
    expect(_panel(page, STEP_CONFIRM)).to_contain_text("autoreset-failing.csv")
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible()

    _step(page, STEP_UPLOAD)
    queue_card = page.locator(".q-card").filter(has=page.get_by_text("Files to import", exact=True))
    expect(queue_card.get_by_text("Failed", exact=True).first).to_be_visible(timeout=10000)

    page.locator('input[type="file"]').set_input_files(str(AUTORESET_SECOND))

    expect(
        page.get_by_text(
            "Previous import cleared from the queue — the failed file was not imported."
        )
    ).to_be_visible(timeout=5000)

    _step(page, STEP_UPLOAD)
    expect(queue_card.get_by_text("autoreset-second.csv").first).to_be_visible(timeout=5000)
    expect(queue_card.get_by_text("autoreset-failing.csv")).to_have_count(0)


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

    _import_now(page)
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
    _wait_for_queue(page, 2)
    _step(page, STEP_UPLOAD)
    expect(page.get_by_text("mbank-2025-10.csv").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("pko-2025-10.csv").first).to_be_visible(timeout=5000)

    # The settings step acts on one file at a time, and the switcher in its
    # header is how the other one is reached — the queue card stays behind on
    # the upload step. Which file is active first depends on which upload
    # handler finished first, so the eyebrow is asked rather than assumed.
    _step(page, STEP_SETTINGS)
    switcher = page.locator("[data-file-switcher]")
    expect(switcher).to_contain_text("of 2", timeout=5000)
    for _ in range(2):
        # The eyebrow is upper-cased by the stylesheet, not by the page.
        eyebrow = page.locator("[data-page-eyebrow]")
        active = eyebrow.inner_text().lower()
        wanted = mbank if "mbank" in active else pko
        _select_import_option(page, "Target account", _account_option(wanted))
        step_back, step_forward = (
            switcher.get_by_role("button").first,
            switcher.get_by_role("button").last,
        )
        moved = step_forward if step_forward.is_enabled() else step_back
        moved.click()
        # The switcher has moved when the header names the other file.
        expect(eyebrow).not_to_contain_text(active.split(" ·")[0], ignore_case=True)

    # Both per-file account chips remain in the queue after switching.
    _step(page, STEP_UPLOAD)
    expect(page.get_by_text(_account_option(mbank)).first).to_be_visible(timeout=5000)
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
    _wait_for_file(page, "mbank-2025-10.csv")

    _step(page, STEP_SETTINGS)
    _select_import_option(page, "Target account", _account_option(account_name))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)
    expect(page.get_by_text("Remember this mapping")).to_be_visible()
    pattern = page.get_by_label("Filename pattern")
    expect(pattern).to_have_value("mbank-*.csv")

    _import_now(page)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)

    rules = list_import_rules()
    assert any(r["filename_pattern"] == "mbank-*.csv" for r in rules)

    page.get_by_role("button", name="Start new import").click()
    page.locator('input[type="file"]').set_input_files(str(MBANK_NOV))
    _wait_for_file(page, "mbank-2025-11.csv")
    _step(page, STEP_UPLOAD)
    expect(page.get_by_text("Rule: mbank-*.csv").first).to_be_visible(timeout=5000)
    _step(page, STEP_SETTINGS)
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

    # Seed an active rule with the real pattern used by uploads, then disable
    # it — along with any other rule of that pattern an earlier import in this
    # shared database remembered, since one left active would match instead.
    seed_import_rule("mbank-*.csv", account_id)
    for rule in list_import_rules():
        if rule["filename_pattern"] == "mbank-*.csv":
            update_import_rule(int(rule["id"]), is_active=False)

    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(MBANK_DEC))
    _wait_for_file(page, "mbank-2025-12.csv")
    # On the step the queue lives on, so "not there" is the rule chip being
    # absent rather than the whole card being off screen.
    _step(page, STEP_UPLOAD)
    queue_card = page.locator(".q-card").filter(has=page.get_by_text("Files to import", exact=True))
    expect(queue_card.get_by_text("mbank-2025-12.csv").first).to_be_visible(timeout=5000)
    expect(queue_card.get_by_text("Rule: mbank-*.csv")).to_have_count(0)

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

    _wait_for_queue(page, 4)
    _step(page, STEP_UPLOAD)
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
    _import_now(page)
    expect(page.get_by_text("Import summary")).to_be_visible(timeout=10000)

    # Coverage and history are not steps: they wait behind one disclosure on
    # the step with nothing else to do.
    _step(page, STEP_FORMAT)
    page.get_by_text("Account coverage and recent imports").click()
    expect(page.get_by_text("Account coverage", exact=True)).to_be_visible(timeout=5000)
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
    expect(page.get_by_role("main").get_by_text("Accounts", exact=True).first).to_be_visible(
        timeout=5000
    )
    expect(page.get_by_text("Last activity").first).to_be_visible()
    expect(page.get_by_text(loaded).first).to_be_visible()
    expect(page.get_by_text("2024-06-15").first).to_be_visible()
    expect(page.get_by_text(empty).first).to_be_visible()


def test_wise_csv_auto_detect_and_import(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-019

    Wise CSV auto-detects, shows JPY metadata, merchant descriptions, and imports.
    """
    account_name = "Wise JPY"
    expense_cat = "Other Expenses Wise E2E"
    income_cat = "Other Income Wise E2E"

    seed_account(account_name, currency="JPY")
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)
    _step(page, STEP_FORMAT)
    expect(page.get_by_role("button", name="Wise")).to_be_visible()

    _step(page, STEP_UPLOAD)
    page.locator('input[type="file"]').set_input_files(str(WISE_JPY))
    _wait_for_file(page, "jpy-travel-sample.csv")
    # The metadata banner belongs with the file, which is the upload step.
    _step(page, STEP_UPLOAD)
    expect(page.get_by_text("JPY").first).to_be_visible(timeout=5000)

    _step(page, STEP_SETTINGS)
    _select_import_option(page, "Target account", _account_option(account_name, "JPY"))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    _step(page, STEP_PREVIEW)
    expect(
        _panel(page, STEP_PREVIEW).get_by_text("Japanpost Bank(245950) GIFU", exact=False).first
    ).to_be_visible(timeout=5000)
    _run_import(page)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(_panel(page, STEP_CONFIRM).get_by_text("imported", exact=False).first).to_be_visible(
        timeout=5000
    )

    page.goto(f"{base_url}/transactions")
    search_ledger(page, "Japanpost Bank(245950) GIFU")
    expect(page.get_by_text("Japanpost Bank(245950) GIFU").first).to_be_visible(timeout=5000)


def test_wise_qif_auto_detect_and_import(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-022

    Wise QIF auto-detects into the Wise profile, banners the statement period
    and the currency read off the download name (the format itself carries
    none), keeps the card-holder memo out of the page, and imports with the
    English payee as description.
    """
    account_name = "Wise JPY QIF"
    expense_cat = "Other Expenses Wise QIF E2E"
    income_cat = "Other Income Wise QIF E2E"

    seed_account(account_name, currency="JPY")
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)

    _step(page, STEP_FORMAT)
    wise_button = page.get_by_role("button", name="Wise")
    expect(wise_button).to_be_visible()

    _step(page, STEP_UPLOAD)
    page.locator('input[type="file"]').set_input_files(
        _upload_as(WISE_JPY_QIF, WISE_QIF_DOWNLOAD_NAME)
    )
    _wait_for_file(page, WISE_QIF_DOWNLOAD_NAME)

    # Auto-detection promoted the upload to Wise: the format picker fills
    # that chip and leaves the others outlined.
    _step(page, STEP_FORMAT)
    expect(wise_button).to_have_class(re.compile(r"k-format-chip--on"), timeout=5000)
    expect(page.get_by_role("button", name="Generic CSV")).not_to_have_class(
        re.compile(r"k-format-chip--on")
    )

    # The QIF body names no currency; the download name does, and that is what
    # the banner shows. The period stays record-derived: the name asks for
    # 04-01 – 06-30, the transactions actually run 04-17 – 05-17.
    _step(page, STEP_UPLOAD)
    banner = page.locator(".k-info-banner").first
    expect(banner).to_contain_text("2026-04-17 – 2026-05-17", timeout=5000)
    expect(banner).to_contain_text("JPY")
    expect(banner).not_to_contain_text("2026-04-01")
    expect(banner).not_to_contain_text("2026-06-30")

    # ``M`` is the card holder and last four on every card row — it must not
    # reach the preview, and below, not the ledger either.
    expect(page.get_by_text("Jan Kowalski", exact=False)).to_have_count(0)

    _step(page, STEP_SETTINGS)
    _select_import_option(page, "Target account", _account_option(account_name, "JPY"))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    _step(page, STEP_PREVIEW)
    expect(
        _panel(page, STEP_PREVIEW).get_by_text("Japanpost Bank(245950) GIFU", exact=False).first
    ).to_be_visible(timeout=5000)
    _run_import(page)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(_panel(page, STEP_CONFIRM).get_by_text("imported", exact=False).first).to_be_visible(
        timeout=5000
    )

    page.goto(f"{base_url}/transactions")
    search_ledger(page, "Topped up account")
    expect(page.get_by_text("Topped up account").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Jan Kowalski", exact=False)).to_have_count(0)


def test_wise_qif_currency_from_name_blocks_the_wrong_account(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-023

    The QIF body names no currency, so before the download name was read a JPY
    statement landed on a PLN account and was booked as PLN. It must be blocked.
    """
    account_name = "Wise PLN Guard"
    expense_cat = "Other Expenses Wise Guard E2E"
    income_cat = "Other Income Wise Guard E2E"

    account_id = seed_account(account_name, currency="PLN")
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)

    page.locator('input[type="file"]').set_input_files(
        _upload_as(WISE_JPY_QIF, WISE_QIF_DOWNLOAD_NAME)
    )
    _wait_for_file(page, WISE_QIF_DOWNLOAD_NAME)

    _step(page, STEP_SETTINGS)
    _select_import_option(page, "Target account", _account_option(account_name, "PLN"))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    # The guard is the same one the import button used to hit; on a wizard it
    # is hit a step earlier, on the card where the account was chosen, and
    # the preview beyond it cannot be reached at all.
    expect(_blocked_reason(page)).to_contain_text(
        "Import blocked: file currency (JPY) does not match account currency (PLN).",
        timeout=10000,
    )
    expect(page.locator("[data-continue]")).to_be_disabled()
    assert count_transactions(account_id) == 0


def test_wise_qif_renamed_upload_is_unknown_and_still_imports(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-024

    Reading the name is best-effort. A renamed download yields no currency, and
    unknown must never block — refusing would leave that file no way in at all.
    """
    account_name = "Wise PLN Renamed"
    expense_cat = "Other Expenses Wise Renamed E2E"
    income_cat = "Other Income Wise Renamed E2E"

    account_id = seed_account(account_name, currency="PLN")
    seed_category(expense_cat)
    seed_income_category(income_cat)

    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)

    page.locator('input[type="file"]').set_input_files(_upload_as(WISE_JPY_QIF, "foo.qif"))
    _wait_for_file(page, "foo.qif")

    # No name to read a currency off, so the banner leaves it blank — exactly
    # as it did before the guard learned to read download names.
    _step(page, STEP_UPLOAD)
    banner = page.locator(".k-info-banner").first
    expect(banner).to_contain_text("2026-04-17 – 2026-05-17", timeout=5000)
    expect(banner).not_to_contain_text("JPY")

    _step(page, STEP_SETTINGS)
    _select_import_option(page, "Target account", _account_option(account_name, "PLN"))
    _select_import_option(page, "Default expense category", expense_cat)
    _select_import_option(page, "Default income category", income_cat)

    _import_now(page)
    expect(page.get_by_text("Import summary", exact=True)).to_be_visible(timeout=10000)
    expect(_panel(page, STEP_CONFIRM).get_by_text("imported", exact=False).first).to_be_visible(
        timeout=5000
    )
    assert count_transactions(account_id) > 0


# ---------------------------------------------------------------------------
# Artboard 2d: the mapping step shows the file it is mapping
# ---------------------------------------------------------------------------


def test_auto_detected_columns_are_marked(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-025

    The importer guesses date, amount and description from the headers, and
    the one thing the old screen could not tell you was which fields it had
    guessed. Changing a picker by hand takes its mark away.
    """
    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))
    _wait_for_file(page, "test_import.csv")
    _step(page, STEP_MAPPING)

    # Asserted per field rather than as a total: a saved import rule from an
    # earlier test in this shared database can fill the mapping instead of
    # detection, which changes how many pills there are but not which fields
    # the importer filled in.
    def badge(field: str) -> Locator:
        return page.locator(f'.k-auto-badge[data-auto-field="{field}"]')

    for field in ("date", "amount", "description"):
        expect(badge(field)).to_be_visible(timeout=10000)

    # Point the description picker somewhere else: it is no longer the guess.
    _select_import_option(page, "Description column", "1: date")
    expect(badge("description")).to_be_hidden(timeout=10000)
    # And only that one: the pills are per field, not a single switch.
    expect(badge("date")).to_be_visible()
    expect(badge("amount")).to_be_visible()


def test_parse_failures_are_named_on_the_mapping_step(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-026

    Two of five rows cannot be read. The strip says so where the columns that
    caused it are being chosen, rather than at Preview, one step too late.
    """
    page.goto(f"{base_url}/import")
    page.locator('input[type="file"]').set_input_files(str(FIXTURES / "partly-unparseable.csv"))
    _wait_for_file(page, "partly-unparseable.csv")
    _step(page, STEP_MAPPING)

    # Rows 3 and 5 of the file: the bad amount and the bad date. The numbers
    # are the point — "some rows failed" sends the reader back to the file to
    # find out which.
    strip = page.locator(".k-warning-strip")
    expect(strip).to_be_visible(timeout=10000)
    expect(strip).to_contain_text("Rows that could not be parsed (2): 3, 5")
    # And it points at the step it is standing on: the columns being mapped.
    expect(strip).to_contain_text("columns you mapped")

    # Above the pickers, which is the whole point of moving it off Preview —
    # it is read on the way into the thing it is asking you to change.
    strip_box = strip.bounding_box()
    picker_box = page.locator(".q-select").filter(has_text="Date column").first.bounding_box()
    assert strip_box is not None and picker_box is not None
    assert strip_box["y"] + strip_box["height"] <= picker_box["y"], (strip_box, picker_box)


def test_the_progress_line_says_which_step_i_am_on(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-027"""
    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)

    # Nothing uploaded: step 2 is the one you are on, step 1 is behind you.
    expect(page.locator(".k-step--now")).to_have_count(1, timeout=5000)
    # And the node says which step it is, not just its number: a screen
    # reader on "2" would otherwise be told nothing at all.
    expect(page.locator('.k-step--now[aria-label="Upload"]')).to_have_count(1)
    expect(page.locator(".k-step--done")).to_have_count(1)

    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))
    _wait_for_file(page, "test_import.csv")

    # Parsed: the line moved on, and exactly one node is still the one you
    # are standing on. How far it moved depends on what the page could infer
    # (a single account fills the settings step in), so this asserts the
    # movement rather than a step number the environment decides.
    expect(page.locator(".k-step--done")).not_to_have_count(1, timeout=10000)
    expect(page.locator(".k-step--now")).to_have_count(1)
    assert page.locator(".k-step--done").count() > 1

    # "The ones behind it are ticked" is a claim about order, not a count:
    # every ticked node comes before the one being stood on.
    states = page.eval_on_selector_all(
        ".k-step",
        "nodes => nodes.map(n => n.classList.contains('k-step--now') ? 'now'"
        " : n.classList.contains('k-step--done') ? 'done' : 'ahead')",
    )
    assert states.index("now") == states.count("done"), states
    assert "done" not in states[states.index("now") :], states

    # And the sample sits *beside* the pickers that map it, headers numbered
    # the way the pickers number them — not above them, as it used to.
    _step(page, STEP_MAPPING)
    # Scoped to the sample table: the Date picker renders its value the same
    # way, so an unscoped match would compare the picker against itself.
    header_cell = page.locator(".k-table thead").get_by_text("1: date", exact=True).first
    expect(header_cell).to_be_visible(timeout=5000)
    sample_box = header_cell.bounding_box()
    picker_box = page.locator(".q-select").filter(has_text="Date column").first.bounding_box()
    assert sample_box is not None and picker_box is not None
    assert sample_box["x"] + sample_box["width"] <= picker_box["x"], (sample_box, picker_box)
    # Side by side means they share vertical space, not that one follows the
    # other down the page.
    assert sample_box["y"] < picker_box["y"] + picker_box["height"]


def test_one_step_is_on_screen_and_back_returns_to_the_one_before(
    page: Page, base_url: str
) -> None:
    """Covers: KAL-CSV-028

    The progress line said "step 3 of 6" over a scroll holding all six. Now
    it names the one card that is there, and walking back is how you fix a
    typo rather than starting the import again.
    """
    page.goto(f"{base_url}/import")
    expect(page.get_by_text("Import Transactions", exact=True).first).to_be_visible(timeout=5000)

    page.locator('input[type="file"]').set_input_files(str(UNRECOGNISED_CSV))
    _wait_for_file(page, "unrecognised_headers.csv")

    def visible_panels() -> list[str]:
        return page.eval_on_selector_all(
            "[data-step-panel]",
            "nodes => nodes.filter(n => n.offsetParent !== null).map(n => n.dataset.stepPanel)",
        )

    # The mapping step, and that is the only card on screen.
    _step(page, STEP_MAPPING)
    assert visible_panels() == [str(STEP_MAPPING)], visible_panels()

    # Something to lose: a column mapped by hand on the step being left.
    _select_import_option(page, "Date column", "1: Txn Day")
    date_picker = page.locator(".q-select").filter(has_text="Date column")
    expect(date_picker).to_contain_text("1: Txn Day")

    # Back walks to the step before it, and the file survives the walk.
    page.locator("[data-wizard-footer]").get_by_role("button", name="Back").click()
    expect(_panel(page, STEP_UPLOAD)).to_be_visible(timeout=5000)
    assert visible_panels() == [str(STEP_UPLOAD)], visible_panels()
    expect(page.get_by_text("unrecognised_headers.csv").first).to_be_visible()

    # The line keeps marking where the work is while ringing where the
    # reader is, so a reader standing behind it can still see both.
    expect(page.locator(".k-step--reading")).to_have_count(1)
    expect(page.locator(".k-step--now")).to_have_count(1)

    # And a step the file has already passed is clickable, in either
    # direction — including back to the format picker, which is step one.
    _step(page, STEP_FORMAT)
    assert visible_panels() == [str(STEP_FORMAT)], visible_panels()
    expect(page.locator("[data-wizard-footer]").get_by_role("button", name="Back")).to_be_disabled()
    _step(page, STEP_MAPPING)
    assert visible_panels() == [str(STEP_MAPPING)], visible_panels()
    # And the column mapped before the walk is still mapped after it.
    expect(date_picker).to_contain_text("1: Txn Day")

    # A bank profile has no mapping step — its columns are the profile's —
    # so that node is ticked but not a link: clicking it would land the
    # reader on a step the file does not have. Uploaded under a name no
    # saved rule in this shared database matches, since a rule that fills
    # the mapping in is a rule that keeps the file on the generic path.
    page.locator('input[type="file"]').set_input_files(
        _upload_as(WISE_JPY_QIF, "kal-csv-028-wise-statement.qif")
    )
    _wait_for_queue(page, 2)
    # Dropped from a step of the reader's own choosing, so it waits in the
    # queue until they click it.
    _step(page, STEP_UPLOAD)
    page.locator('[data-queue-row="kal-csv-028-wise-statement.qif"]').click()
    _wait_for_file(page, "kal-csv-028-wise-statement.qif")
    expect(page.locator('[data-step="2"]')).to_have_class(re.compile(r"cursor-pointer"))
    expect(page.locator('[data-step="3"]')).not_to_have_class(re.compile(r"cursor-pointer"))


def test_a_late_upload_does_not_take_the_step_you_chose(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-028

    A multi-file drop runs one upload handler per file, and each one ends by
    putting the page where its own file is. A reader who walks to a step
    while the rest are still parsing keeps it: the page follows the work
    only while nobody has chosen for themselves.
    """
    page.goto(f"{base_url}/import")
    expect(_panel(page, STEP_UPLOAD)).to_be_visible(timeout=10000)

    page.locator('input[type="file"]').set_input_files(str(OTHER_A))
    _wait_for_file(page, "other-a.csv")

    # The reader goes somewhere of their own choosing.
    _step(page, STEP_FORMAT)

    # A second file lands. It joins the queue — the page is not pretending
    # it did not arrive — but it takes neither the step nor the screen: a
    # reader reading one file does not want another swapped in under them.
    page.locator('input[type="file"]').set_input_files(str(OTHER_B))
    _wait_for_queue(page, 2)

    visible = page.eval_on_selector_all(
        "[data-step-panel]",
        "nodes => nodes.filter(n => n.offsetParent !== null).map(n => n.dataset.stepPanel)",
    )
    assert visible == [str(STEP_FORMAT)], visible
    expect(page.locator("[data-page-eyebrow]")).to_contain_text("other-a.csv", ignore_case=True)
    _step(page, STEP_UPLOAD)
    expect(page.get_by_text("other-b.csv").first).to_be_visible()


def test_continue_refuses_an_unfinished_step_and_says_why(page: Page, base_url: str) -> None:
    """Covers: KAL-CSV-029

    A disabled button that does not say why is the worst thing a wizard can
    do — every refusal here is the message the import itself would give.
    """
    account_name = "Continue Refuses Account"
    seed_account(account_name)
    seed_category("Other Expenses Refuses")
    seed_income_category("Other Income Refuses")

    page.goto(f"{base_url}/import")
    expect(_panel(page, STEP_UPLOAD)).to_be_visible(timeout=10000)

    # Nothing uploaded: the upload step is waiting on a file, and says so.
    expect(page.locator("[data-continue]")).to_be_disabled()
    expect(_blocked_reason(page)).to_have_text("Upload a file to continue.")

    page.locator('input[type="file"]').set_input_files(str(IMPORT_CSV))
    _wait_for_file(page, "test_import.csv")

    # Parsed but with nowhere to put the rows: the settings step refuses in
    # the readiness check's own words, not with the file's last piece of news
    # ("Loaded 3 rows.", which answers a question nobody asked). Which of the
    # three it names depends on what the page could infer — a saved rule from
    # an earlier test in this shared database fills the account in — so the
    # claim is that the refusal names a setting, and moves on as each is made.
    _step(page, STEP_SETTINGS)
    expect(page.locator("[data-continue]")).to_be_disabled()
    expect(_blocked_reason(page)).to_contain_text("Select a")

    _select_import_option(page, "Target account", _account_option(account_name))
    expect(_blocked_reason(page)).to_contain_text("Select a default", timeout=5000)
    _select_import_option(page, "Default expense category", "Other Expenses Refuses")
    # The last one is asserted whole: by here nothing about the shared
    # database can change which setting is missing.
    expect(_blocked_reason(page)).to_have_text("Select a default income category.", timeout=5000)
    _select_import_option(page, "Default income category", "Other Income Refuses")

    # Everything chosen: the step is finished, so Continue stops refusing and
    # the reason it was giving is gone.
    expect(page.locator("[data-continue]")).to_be_enabled(timeout=5000)
    expect(_blocked_reason(page)).to_have_count(0)
    _continue(page)
    expect(_panel(page, STEP_PREVIEW)).to_be_visible(timeout=5000)
