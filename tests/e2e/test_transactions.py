# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Manual Transaction Entry.

Covers: KAL-TXN-001, KAL-TXN-009, KAL-TXN-010, KAL-TXN-011, KAL-TXN-012,
KAL-TXN-013, KAL-TXN-014, KAL-TXN-015, KAL-TXN-016, KAL-TXN-017,
KAL-PAG-005

Maps the q3-test-safety-net flow: add, edit, and split a transaction.
Page URL: /transactions
"""

from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e.ledger import pick_open_menu_option, search_ledger
from tests.e2e.seed_helpers import (
    get_transaction,
    seed_account,
    seed_category,
    seed_payee,
    seed_transaction,
    seed_transfer_pair,
)


def _fill_number(scope: Page, label: str, value: str) -> None:
    field = scope.get_by_role("spinbutton", name=label, exact=True)
    field.click(click_count=3)
    field.fill(value)


def _set_split_amount(field: Locator, value: str) -> None:
    """Type a split line's amount and commit it.

    NiceGUI syncs a number input on `change`, so a `fill` that is never blurred
    leaves the server still holding the old figure — and "Fill last", which
    balances against the server's model, then writes a last line that does not
    add up to the total. The Save button stays disabled for good, 30s of
    Playwright auto-waiting included. Tab commits the value first.
    """
    field.click(click_count=3)
    field.fill(value)
    field.press("Tab")


def _save_when_balanced(dialog: Page) -> None:
    """Save once the dialog agrees the split lines add up.

    Save is disabled while they do not, and it is re-enabled over the
    websocket, so clicking it in the same breath as "Fill last" races that
    round trip.
    """
    save = dialog.get_by_role("button", name="Save")
    expect(save).to_be_enabled(timeout=10000)
    save.click()


def _select_option(page: Page, dialog: Page, select_index: int, option: str) -> None:
    """Open a Quasar select by position and pick an option."""
    dialog.locator(".q-select").nth(select_index).click()
    pick_open_menu_option(page, option)


def _select_labeled(page: Page, dialog: Page, label: str, option: str) -> None:
    """Open a Quasar select by its label and pick an option."""
    dialog.get_by_label(label).click()
    pick_open_menu_option(page, option)


def _find_row(page: Page, description: str):  # noqa: ANN201
    """Locate a ledger row by description, filtering so paging cannot hide it."""
    search_ledger(page, description)
    return page.locator(".q-table tbody tr").filter(has_text=description)


def test_add_edit_split_transaction(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-001, KAL-SPL-001, KAL-SPL-004

    Exercises the full manual-entry flow — add an expense, edit its
    description and amount, then create a split transaction across two
    categories and edit the saved split lines.
    """
    account_name = "PKO Main Tx E2E"
    food_cat = "Food Tx E2E"
    split_cat_a = "Food Split A Tx E2E"
    split_cat_b = "Food Split B Tx E2E"

    seed_account(account_name)
    seed_category(food_cat)
    seed_category(split_cat_a)
    seed_category(split_cat_b)

    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    # ── Add expense ───────────────────────────────────────────────────────
    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "45.50")
    dialog.get_by_label("Description (optional)").fill("Supermarket Tx E2E")
    dialog.get_by_label("Category").click()
    page.locator(".q-menu").get_by_text(food_cat, exact=True).click()
    dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Supermarket Tx E2E").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("-45.50").first).to_be_visible(timeout=5000)

    # ── Edit ──────────────────────────────────────────────────────────────
    row = page.locator(".q-table tbody tr").filter(has_text="Supermarket Tx E2E")
    row.get_by_role("button", name="Edit").click()

    edit_dialog = page.get_by_role("dialog")
    expect(edit_dialog.get_by_text("Edit Transaction", exact=True)).to_be_visible(timeout=5000)

    desc_field = edit_dialog.get_by_label("Description (optional)")
    desc_field.click(click_count=3)
    desc_field.fill("Supermarket Updated Tx E2E")
    _fill_number(edit_dialog, "Amount", "50.00")
    edit_dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Supermarket Updated Tx E2E").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("-50.00").first).to_be_visible(timeout=5000)

    # ── Split ─────────────────────────────────────────────────────────────
    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "100")
    dialog.get_by_label("Description (optional)").fill("Split Grocery Tx E2E")
    dialog.get_by_text("Split", exact=True).click()

    split_rows = dialog.locator(".split-cat-select")
    expect(split_rows).to_have_count(2, timeout=5000)

    split_rows.nth(0).click()
    page.locator(".q-menu").get_by_text(split_cat_a, exact=True).click()
    split_rows.nth(1).click()
    page.locator(".q-menu").get_by_text(split_cat_b, exact=True).click()

    split_amount_fields = dialog.locator(".split-cat-select").locator(
        "xpath=ancestor::div[contains(@class,'row')][1]//input[@type='number']"
    )
    _set_split_amount(split_amount_fields.first, "60")
    dialog.get_by_role("button", name="Fill last").click()

    _save_when_balanced(dialog)

    expect(page.get_by_text("Split Grocery Tx E2E").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("-100.00").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Split (2)", exact=True).first).to_be_visible(timeout=5000)
    expect(
        page.locator(".q-table tbody tr")
        .filter(has_text="Split Grocery Tx E2E")
        .locator(".split-row-icon")
    ).to_be_visible(timeout=5000)

    # ── Edit split ────────────────────────────────────────────────────────
    split_row = page.locator(".q-table tbody tr").filter(has_text="Split Grocery Tx E2E")
    split_row.get_by_role("button", name="Edit").click()

    split_edit_dialog = page.get_by_role("dialog")
    expect(split_edit_dialog.get_by_text("Edit Transaction", exact=True)).to_be_visible(
        timeout=5000
    )

    split_amount_fields = split_edit_dialog.locator(".split-cat-select").locator(
        "xpath=ancestor::div[contains(@class,'row')][1]//input[@type='number']"
    )
    _set_split_amount(split_amount_fields.nth(0), "70")
    _set_split_amount(split_amount_fields.nth(1), "30")
    _save_when_balanced(split_edit_dialog)

    expect(page.get_by_text("Split Grocery Tx E2E").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("-100.00").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("Split (2)", exact=True).first).to_be_visible(timeout=5000)


def test_split_row_indicator_and_plain_row(page: Page, base_url: str) -> None:
    """Covers: KAL-SPL-005

    After creating a split and a plain expense, only the split row shows
    the call_split icon and ``Split (2)`` category label.
    """
    account_name = "PKO Split Ind E2E"
    plain_cat = "Food Plain Ind E2E"
    split_cat_a = "Food SplitA Ind E2E"
    split_cat_b = "Food SplitB Ind E2E"

    seed_account(account_name)
    seed_category(plain_cat)
    seed_category(split_cat_a)
    seed_category(split_cat_b)

    # Plain expense
    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "20.00")
    dialog.get_by_label("Description (optional)").fill("Plain Ind E2E")
    dialog.get_by_label("Category").click()
    page.locator(".q-menu").get_by_text(plain_cat, exact=True).click()
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Plain Ind E2E").first).to_be_visible(timeout=5000)

    # Split expense
    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "100")
    dialog.get_by_label("Description (optional)").fill("Split Ind E2E")
    dialog.get_by_text("Split", exact=True).click()
    split_rows = dialog.locator(".split-cat-select")
    expect(split_rows).to_have_count(2, timeout=5000)
    split_rows.nth(0).click()
    page.locator(".q-menu").get_by_text(split_cat_a, exact=True).click()
    split_rows.nth(1).click()
    page.locator(".q-menu").get_by_text(split_cat_b, exact=True).click()
    split_amount_fields = dialog.locator(".split-cat-select").locator(
        "xpath=ancestor::div[contains(@class,'row')][1]//input[@type='number']"
    )
    _set_split_amount(split_amount_fields.first, "60")
    dialog.get_by_role("button", name="Fill last").click()
    _save_when_balanced(dialog)

    split_row = page.locator(".q-table tbody tr").filter(has_text="Split Ind E2E")
    plain_row = page.locator(".q-table tbody tr").filter(has_text="Plain Ind E2E")

    expect(split_row.get_by_text("Split (2)", exact=True)).to_be_visible(timeout=5000)
    expect(split_row.locator(".split-row-icon")).to_be_visible(timeout=5000)
    expect(plain_row.get_by_text(plain_cat, exact=True)).to_be_visible(timeout=5000)
    expect(plain_row.locator(".split-row-icon")).to_have_count(0)
    expect(plain_row.get_by_text("Split (2)", exact=True)).to_have_count(0)


def test_split_row_action_prearms_editor(page: Page, base_url: str) -> None:
    """Covers: KAL-SPL-006

    The row Split action opens the edit dialog with the split switch ON;
    saving two balanced lines then shows the table indicator.
    """
    account_name = "PKO Split Act E2E"
    food_cat = "Food Act E2E"
    split_cat_a = "Food SplitA Act E2E"
    split_cat_b = "Food SplitB Act E2E"

    seed_account(account_name)
    seed_category(food_cat)
    seed_category(split_cat_a)
    seed_category(split_cat_b)

    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "80.00")
    dialog.get_by_label("Description (optional)").fill("Arm Split E2E")
    dialog.get_by_label("Category").click()
    page.locator(".q-menu").get_by_text(food_cat, exact=True).click()
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Arm Split E2E").first).to_be_visible(timeout=5000)

    row = page.locator(".q-table tbody tr").filter(has_text="Arm Split E2E")
    row.get_by_role("button", name="Split").click()

    edit_dialog = page.get_by_role("dialog")
    expect(edit_dialog.get_by_text("Edit Transaction", exact=True)).to_be_visible(timeout=5000)
    expect(edit_dialog.locator(".split-cat-select")).to_have_count(2, timeout=5000)
    expect(edit_dialog.get_by_role("switch")).to_be_checked()
    expect(edit_dialog.get_by_role("button", name="Fill last")).to_be_visible()

    split_rows = edit_dialog.locator(".split-cat-select")
    split_rows.nth(0).click()
    page.locator(".q-menu").get_by_text(split_cat_a, exact=True).click()
    split_rows.nth(1).click()
    page.locator(".q-menu").get_by_text(split_cat_b, exact=True).click()

    split_amount_fields = edit_dialog.locator(".split-cat-select").locator(
        "xpath=ancestor::div[contains(@class,'row')][1]//input[@type='number']"
    )
    _set_split_amount(split_amount_fields.first, "50")
    edit_dialog.get_by_role("button", name="Fill last").click()
    _save_when_balanced(edit_dialog)

    updated = page.locator(".q-table tbody tr").filter(has_text="Arm Split E2E")
    expect(updated.get_by_text("Split (2)", exact=True)).to_be_visible(timeout=5000)
    expect(updated.locator(".split-row-icon")).to_be_visible(timeout=5000)


def test_add_note_then_clear_it(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-007, KAL-TXN-008

    A transaction saved with a long-form note shows the note icon and the note
    text on hover; clearing the textarea on edit removes the indicator again.
    """
    account_name = "PKO Notes E2E"
    category_name = "Food Notes E2E"
    described = "Gift Notes E2E"

    account_id = seed_account(account_name)
    category_id = seed_category(category_name)

    # ── KAL-TXN-007: add with a note ──────────────────────────────────────
    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "120.00")
    dialog.get_by_label("Description (optional)").fill(described)

    # Alt+Shift+N jumps to the notes textarea from any other field (Ctrl+Shift+N
    # is bound too but Chrome claims it for a new incognito window).
    page.keyboard.press("Alt+Shift+KeyN")
    expect(dialog.get_by_label("Notes (optional)")).to_be_focused(timeout=5000)
    page.keyboard.type("Bought for mum's birthday")
    dialog.get_by_label("Category").click()
    page.locator(".q-menu").get_by_text(category_name, exact=True).click()
    dialog.get_by_role("button", name="Save").click()

    row = page.locator(".q-table tbody tr").filter(has_text=described)
    expect(row).to_have_count(1, timeout=5000)
    note_icon = row.locator(".notes-row-icon")
    expect(note_icon).to_be_visible(timeout=5000)

    note_icon.hover()
    expect(page.locator(".q-tooltip").filter(has_text="Bought for mum's birthday")).to_be_visible(
        timeout=5000
    )

    # ── KAL-TXN-008: clear the note ───────────────────────────────────────
    seeded = "Receipt Notes E2E"
    seed_transaction(
        account_id,
        category_id,
        25.0,
        description=seeded,
        notes="Receipt #123",
    )
    page.goto(f"{base_url}/transactions")
    seeded_row = page.locator(".q-table tbody tr").filter(has_text=seeded)
    expect(seeded_row.locator(".notes-row-icon")).to_be_visible(timeout=5000)

    seeded_row.get_by_role("button", name="Edit").click()
    edit_dialog = page.get_by_role("dialog")
    expect(edit_dialog.get_by_text("Edit Transaction", exact=True)).to_be_visible(timeout=5000)

    notes_field = edit_dialog.get_by_label("Notes (optional)")
    expect(notes_field).to_have_value("Receipt #123", timeout=5000)
    notes_field.fill("")
    edit_dialog.get_by_role("button", name="Save").click()

    expect(page.get_by_text("Transaction updated.").first).to_be_visible(timeout=5000)
    seeded_row = page.locator(".q-table tbody tr").filter(has_text=seeded)
    expect(seeded_row.locator(".notes-row-icon")).to_have_count(0, timeout=5000)


PAYEE_LABEL = "Payee (optional)"


def _pick_payee(page: Page, dialog: Page, query: str, option: str) -> None:
    """Type into the payee combobox and pick a matching existing payee."""
    field = dialog.get_by_label(PAYEE_LABEL)
    field.click()
    field.fill(query)
    menu = page.locator(".q-menu").last
    expect(menu).to_be_visible(timeout=3000)
    menu.get_by_text(option, exact=True).first.click()


def test_payee_pick_fills_last_used_category(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-009

    Picking a known payee fills the category it was last booked to, and says so.
    """
    account_name = "PKO Payee E2E"
    food_cat = "Zywnosc Payee E2E"
    payee_name = "Biedronka Payee E2E"

    account_id = seed_account(account_name)
    food_id = seed_category(food_cat)
    payee_id = seed_payee(payee_name)
    seed_transaction(account_id, food_id, 42.0, payee_id=payee_id, description="prior")

    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "18.00")
    _pick_payee(page, dialog, "biedr", payee_name)

    expect(dialog.get_by_label("Category")).to_have_value(food_cat, timeout=5000)
    expect(page.get_by_text("Filled", exact=False).first).to_be_visible(timeout=5000)


def test_payee_autofill_keeps_chosen_category(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-010

    A category the user picked first is a decision, not an empty field.
    """
    account_name = "PKO Keep E2E"
    food_cat = "Zywnosc Keep E2E"
    other_cat = "Chemia Keep E2E"
    payee_name = "Biedronka Keep E2E"

    account_id = seed_account(account_name)
    food_id = seed_category(food_cat)
    seed_category(other_cat)
    payee_id = seed_payee(payee_name)
    seed_transaction(account_id, food_id, 42.0, payee_id=payee_id, description="prior")

    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "18.00")
    _select_labeled(page, dialog, "Category", other_cat)
    _pick_payee(page, dialog, "biedr", payee_name)

    expect(dialog.get_by_label("Category")).to_have_value(other_cat, timeout=5000)


def test_typing_unknown_payee_creates_it_on_save(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-011

    A name that matches nothing is created with the transaction, so the user
    never has to leave the dialog to register a payee first.
    """
    account_name = "PKO New Payee E2E"
    category_name = "Restauracje New Payee E2E"
    payee_name = "Pasibus New Payee E2E"
    described = "Burger New Payee E2E"

    seed_account(account_name)
    seed_category(category_name)

    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    _select_option(page, dialog, 1, account_name)
    _fill_number(dialog, "Amount", "39.00")
    dialog.get_by_label("Description (optional)").fill(described)
    payee_field = dialog.get_by_label(PAYEE_LABEL)
    payee_field.click()
    payee_field.fill(payee_name)
    payee_field.press("Enter")
    _select_labeled(page, dialog, "Category", category_name)
    dialog.get_by_role("button", name="Save").click()

    expect(_find_row(page, described)).to_have_count(1, timeout=5000)

    page.goto(f"{base_url}/payees")
    expect(page.get_by_text(payee_name, exact=True).first).to_be_visible(timeout=5000)


def test_edit_shows_payee_and_fills_nothing(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-012

    The edit dialog carries the payee, but never rewrites a saved row's category.
    """
    import datetime

    account_name = "PKO Edit Payee E2E"
    food_cat = "Zywnosc Edit Payee E2E"
    other_cat = "Chemia Edit Payee E2E"
    payee_name = "Biedronka Edit Payee E2E"
    described = "Older Edit Payee E2E"

    account_id = seed_account(account_name)
    food_id = seed_category(food_cat)
    other_id = seed_category(other_cat)
    payee_id = seed_payee(payee_name)
    seed_transaction(
        account_id,
        other_id,
        12.0,
        date=datetime.date(2025, 1, 5),
        payee_id=payee_id,
        description=described,
    )
    seed_transaction(
        account_id,
        food_id,
        30.0,
        date=datetime.date(2025, 8, 5),
        payee_id=payee_id,
        description="newer Edit Payee E2E",
    )

    page.goto(f"{base_url}/transactions")
    row = _find_row(page, described)
    expect(row).to_have_count(1, timeout=5000)
    row.get_by_role("button", name="Edit").click()

    edit_dialog = page.get_by_role("dialog")
    expect(edit_dialog.get_by_text("Edit Transaction", exact=True)).to_be_visible(timeout=5000)
    expect(edit_dialog.get_by_label(PAYEE_LABEL)).to_have_value(payee_name, timeout=5000)
    expect(edit_dialog.get_by_label("Category")).to_have_value(other_cat, timeout=5000)


def test_editing_a_transfer_has_no_payee_field(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-013

    A transfer between own accounts has no counterparty, so the payee field is
    hidden — and saving must leave the payee an import attached to the leg alone.
    """
    source_name = "PKO Transfer Payee E2E"
    category_name = "Przelewy Transfer Payee E2E"
    payee_name = "Imported Transfer Payee E2E"
    described = "Transfer Payee E2E"

    account_id = seed_account(source_name)
    category_id = seed_category(category_name)
    payee_id = seed_payee(payee_name)
    tx_id = seed_transaction(
        account_id,
        category_id,
        100.0,
        tx_type="transfer",
        payee_id=payee_id,
        description=described,
    )

    page.goto(f"{base_url}/transactions")
    row = _find_row(page, described)
    expect(row).to_have_count(1, timeout=5000)
    row.get_by_role("button", name="Edit").click()

    edit_dialog = page.get_by_role("dialog")
    expect(edit_dialog.get_by_text("Edit Transaction", exact=True)).to_be_visible(timeout=5000)
    # NiceGUI hides with a CSS class, so the fields stay in the DOM.
    expect(edit_dialog.get_by_label(PAYEE_LABEL)).not_to_be_visible(timeout=5000)
    expect(edit_dialog.get_by_label("Category")).not_to_be_visible()

    edit_dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Transaction updated.").first).to_be_visible(timeout=5000)

    assert get_transaction(tx_id)["payee_id"] == payee_id


LEDGER_TOKEN = "LedgerChipsE2E"


def _tick_every_row(page: Page) -> None:
    """Tick each row, waiting for the bar to count it before ticking the next.

    The first tick inserts the selection bar above the table, which moves every
    row down. Clicking straight on through the shift can put the second click
    where the checkbox no longer is, and the bar then never reaches the count
    the scenario asserts.
    """
    for n, checkbox in enumerate(page.locator(".q-table tbody .q-checkbox").all(), start=1):
        checkbox.click()
        expect(page.get_by_text(f"{n} selected", exact=True)).to_be_visible(timeout=10000)


def _filter_by_search(page: Page, base_url: str, token: str, rows: int = 2) -> None:
    """Narrow the ledger to the rows a scenario seeded."""
    page.goto(f"{base_url}/transactions")
    search_ledger(page, token)
    expect(page.locator(".q-table tbody tr")).to_have_count(rows, timeout=10000)


def test_selection_bar_totals_the_selected_rows(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-014

    Two rows from artboard 2a — Lidl at -128,74 and a salary at +9 240,00 —
    net out to +9 111,26 in the selection bar.
    """
    account_id = seed_account("PKO Ledger Total E2E")
    expense_cat = seed_category("Zywnosc Ledger E2E")
    income_cat = seed_category("Wynagrodzenie Ledger E2E", cat_type="income")
    seed_transaction(account_id, expense_cat, 128.74, description=f"Lidl {LEDGER_TOKEN}")
    seed_transaction(
        account_id,
        income_cat,
        9240.00,
        tx_type="income",
        description=f"Salary {LEDGER_TOKEN}",
    )

    _filter_by_search(page, base_url, LEDGER_TOKEN)

    # The chip says what it filtered, and the clear-all link counts it.
    expect(page.locator(".k-chip-search")).to_contain_text(LEDGER_TOKEN)
    expect(page.get_by_text("Clear all 1", exact=True)).to_be_visible()

    _tick_every_row(page)

    # The scenario's own words, kept in the test that covers it.
    expect(page.get_by_text("2 selected", exact=True)).to_be_visible()
    bar = page.locator(".k-selection-bar")
    expect(bar.get_by_text("+9 111.26", exact=True)).to_be_visible(timeout=10000)

    # Dismissing the bar leaves the ledger standing, so it has to take the
    # ticks off the rows itself — a row that still looks selected under no bar
    # sends the whole selection back on the next click.
    ticked = page.locator('.q-table tbody .q-checkbox[aria-checked="true"]')
    expect(ticked).to_have_count(2)
    bar.get_by_role("button", name="Clear selection").click()
    expect(page.get_by_text("2 selected", exact=True)).to_have_count(0, timeout=10000)
    expect(ticked).to_have_count(0, timeout=10000)

    # Clearing the filters redraws the table with nothing ticked — the bar must
    # go with it, or its delete button still points at rows nobody selected.
    _tick_every_row(page)
    page.get_by_role("button", name="Clear all 1").click()
    expect(page.get_by_text("2 selected", exact=True)).to_have_count(0, timeout=10000)


def test_week_separator_shows_the_group_net(page: Page, base_url: str) -> None:
    """Covers: KAL-PAG-005

    The same two rows, grouped by week: the separator carries their net.
    """
    token = "LedgerWeekE2E"
    account_id = seed_account("PKO Ledger Week E2E")
    expense_cat = seed_category("Zywnosc Week E2E")
    income_cat = seed_category("Wynagrodzenie Week E2E", cat_type="income")
    seed_transaction(account_id, expense_cat, 128.74, description=f"Lidl {token}")
    seed_transaction(
        account_id, income_cat, 9240.00, tx_type="income", description=f"Salary {token}"
    )

    _filter_by_search(page, base_url, token)

    # Selecting first: regrouping redraws the table with nothing ticked, so
    # the bar must not survive it holding ids nobody can see are selected.
    _tick_every_row(page)

    page.get_by_role("button", name="Week", exact=True).click()

    expect(page.get_by_text("2 selected", exact=True)).to_have_count(0, timeout=10000)
    separator = page.locator(".k-sep-row")
    expect(separator.first).to_be_visible(timeout=10000)
    expect(separator.first).to_contain_text("+9 111.26")


def test_a_transfer_pair_nets_to_nothing(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-015

    Both legs of an internal transfer are booked, so the column shows two
    outflows — but nothing left the user, and the total has to say so.
    """
    token = "LedgerTransferE2E"
    out_account = seed_account("PKO Ledger Transfer E2E")
    in_account = seed_account("mBank Ledger Transfer E2E")
    category_id = seed_category("Przelewy Ledger E2E")
    seed_transfer_pair(out_account, in_account, category_id, 1500.00, f"Own {token}")

    _filter_by_search(page, base_url, token)

    _tick_every_row(page)

    total = page.locator(".k-selection-bar").get_by_text("0.00", exact=True)
    expect(total).to_be_visible(timeout=10000)
    expect(total).to_have_class(re.compile(r"k-amount--neutral"))

    # One leg on its own says nothing either: the row does not record which
    # way the money went, so the net must not claim a direction for it.
    page.locator(".q-table tbody .q-checkbox").first.click()
    expect(page.get_by_text("1 selected", exact=True)).to_be_visible(timeout=10000)
    expect(total).to_be_visible()
    expect(total).to_have_class(re.compile(r"k-amount--neutral"))


def test_account_chip_filters_shows_its_value_and_clears(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-005, KAL-TXN-016

    The account filter is a multi-select inside a chip's menu now, so this
    drives the whole path: open the chip, pick an account, read the value off
    the chip, and clear it from the chip's own ``×``.
    """
    token = "LedgerAccountE2E"
    mine = f"PKO Chip {token}"
    other = f"mBank Chip {token}"
    mine_id = seed_account(mine)
    other_id = seed_account(other)
    category_id = seed_category(f"Zywnosc Chip {token}")
    seed_transaction(mine_id, category_id, 10.00, description=f"Mine {token}")
    seed_transaction(other_id, category_id, 20.00, description=f"Theirs {token}")

    _filter_by_search(page, base_url, token)

    chip = page.locator(".k-chip-accounts")
    expect(chip).to_contain_text("Accounts")
    chip.click()
    # The chip's menu holds the select; the select opens a menu of its own.
    page.locator(".q-menu").last.locator(".q-select").click()
    pick_open_menu_option(page, mine)
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")

    # The chip says which account, and the ledger holds only its row.
    expect(chip).to_contain_text(mine, timeout=10000)
    expect(page.locator(".q-table tbody tr")).to_have_count(1, timeout=10000)
    expect(page.get_by_text(f"Mine {token}")).to_be_visible()
    # The search chip and the account chip: two filters, one link.
    expect(page.get_by_role("button", name="Clear all 2")).to_be_visible()

    chip.locator(".q-icon", has_text="close").click()

    expect(chip).to_contain_text("Accounts", timeout=10000)
    expect(page.locator(".q-table tbody tr")).to_have_count(2, timeout=10000)


def test_a_chip_opens_from_the_keyboard(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-016

    Every filter moved behind a chip, so a keyboard user has to be able to
    open one — the chips carry tabindex and answer Space, and Quasar's own
    anchor handling answers Enter.
    """
    page.goto(f"{base_url}/transactions")
    chip = page.locator(".k-chip-types")
    expect(chip).to_be_visible(timeout=10000)

    opener = chip.locator('[role="button"]').first
    opener.focus()
    opener.press(" ")

    expect(page.locator(".q-menu").last).to_be_visible(timeout=5000)

    # Enter is Quasar's own anchor handling, not ours — which is exactly why
    # it needs a test: an upgrade could take it away and nothing here would
    # notice, while the scenario still promises a chip opens from the keyboard.
    page.keyboard.press("Escape")
    expect(page.locator(".q-menu")).to_have_count(0, timeout=5000)
    opener.focus()
    opener.press("Enter")
    expect(page.locator(".q-menu").last).to_be_visible(timeout=5000)


def test_a_zero_amount_row_has_no_direction(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-017

    Nothing moved, so the row shows no sign and takes neither amount colour —
    the same rule the group separator and the selection total follow.
    """
    token = "LedgerZeroE2E"
    account_id = seed_account("PKO Ledger Zero E2E")
    category_id = seed_category("Zywnosc Zero E2E")
    seed_transaction(account_id, category_id, 0.00, description=f"Korekta {token}")

    _filter_by_search(page, base_url, token, rows=1)

    amount = page.locator(".q-table tbody tr span.k-amount")
    expect(amount).to_have_text("0.00", timeout=10000)
    expect(amount).to_have_class(re.compile(r"k-amount--neutral"))


def test_a_rows_actions_are_in_reach_without_scrolling_sideways(page: Page, base_url: str) -> None:
    """Covers: KAL-TXN-018

    The edit and split buttons were being rendered and then pushed past the
    right edge of the window: the ledger's table lays itself out
    automatically, and whichever column had the longest content — the tags,
    or a category named like this one — took the slack until the last
    column sat outside the viewport. Only a sideways scroll reached it.
    """
    token = "Reach E2E"
    account_id = seed_account("PKO Konto Glowne Oszczednosciowe Reach E2E")
    long_cat = seed_category("Mieszkanie, media, czynsz i inne oplaty stale miesieczne Reach E2E")
    seed_transaction(account_id, long_cat, 128.74, description=f"Lidl {token}")
    seed_transaction(account_id, long_cat, 42.00, description=f"Zabka {token}")

    # The width artboard `2a` is drawn at, with the drawer it is drawn with:
    # narrower than this the table scrolls sideways by design, and the claim
    # is about the window the design is for.
    page.set_viewport_size({"width": 1360, "height": 900})
    _filter_by_search(page, base_url, token)
    toggle = page.locator("[data-drawer-mini-toggle]")
    if page.locator(".q-drawer--mini").count() == 0:
        toggle.first.click()
        expect(page.locator(".q-drawer--mini")).to_have_count(1, timeout=5000)
    # The class lands when the state flips; the width animates over it. Read
    # the table's box before that finishes and the drawer is still most of
    # the 236px it is shrinking from, which puts the table's right edge past
    # 1360 and fails a claim about the layout on a timing accident. The rail
    # is 64px (`test_dashboard_desktop.MINI_WIDTH`).
    page.wait_for_function(
        """() => {
          const a = document.querySelector('aside.q-drawer');
          return a && Math.round(a.getBoundingClientRect().width) === 64;
        }""",
        timeout=10000,
    )

    row = page.locator(".q-table tbody tr").first
    expect(row.locator(".k-row-action")).to_have_count(2)
    for button in row.locator(".k-row-action").all():
        expect(button).to_be_visible()

    # In reach means on the screen, not merely in the DOM.
    table = page.locator(".k-ledger-card .q-table").first
    box = table.bounding_box()
    assert box is not None
    assert box["x"] + box["width"] <= 1360, (box, "1360")
