# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Manual Transaction Entry.

Covers: KAL-TXN-001, KAL-TXN-009, KAL-TXN-010, KAL-TXN-011, KAL-TXN-012,
KAL-TXN-013

Maps the q3-test-safety-net flow: add, edit, and split a transaction.
Page URL: /transactions
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    get_transaction,
    seed_account,
    seed_category,
    seed_payee,
    seed_transaction,
)


def _fill_number(scope: Page, label: str, value: str) -> None:
    field = scope.get_by_role("spinbutton", name=label, exact=True)
    field.click(click_count=3)
    field.fill(value)


def _pick_open_menu_option(page: Page, option: str) -> None:
    """Pick an option from the open Quasar menu, scrolling virtual lists if needed."""
    menu = page.locator(".q-menu").last
    expect(menu).to_be_visible(timeout=3000)
    target = menu.get_by_text(option, exact=True)
    for _ in range(40):
        if target.count() > 0:
            target.first.click()
            return
        menu.evaluate(
            """(el) => {
              const scroller =
                el.querySelector('.q-virtual-scroll__content')?.parentElement
                || el.querySelector('.scroll')
                || el;
              scroller.scrollTop += 220;
            }"""
        )
        page.wait_for_timeout(40)
    raise AssertionError(f"Select option not found after scrolling: {option!r}")


def _select_option(page: Page, dialog: Page, select_index: int, option: str) -> None:
    """Open a Quasar select by position and pick an option."""
    dialog.locator(".q-select").nth(select_index).click()
    _pick_open_menu_option(page, option)


def _select_labeled(page: Page, dialog: Page, label: str, option: str) -> None:
    """Open a Quasar select by its label and pick an option."""
    dialog.get_by_label(label).click()
    _pick_open_menu_option(page, option)


def _find_row(page: Page, description: str):  # noqa: ANN201
    """Locate a ledger row by description, filtering so paging cannot hide it."""
    search = page.get_by_label("Search description")
    search.click(click_count=3)
    search.fill(description)
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
    split_amount_fields.first.click(click_count=3)
    split_amount_fields.first.fill("60")
    dialog.get_by_role("button", name="Fill last").click()

    dialog.get_by_role("button", name="Save").click()

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
    split_amount_fields.nth(0).click(click_count=3)
    split_amount_fields.nth(0).fill("70")
    split_amount_fields.nth(1).click(click_count=3)
    split_amount_fields.nth(1).fill("30")
    split_edit_dialog.get_by_role("button", name="Save").click()

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
    split_amount_fields.first.click(click_count=3)
    split_amount_fields.first.fill("60")
    dialog.get_by_role("button", name="Fill last").click()
    dialog.get_by_role("button", name="Save").click()

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
    split_amount_fields.first.click(click_count=3)
    split_amount_fields.first.fill("50")
    edit_dialog.get_by_role("button", name="Fill last").click()
    edit_dialog.get_by_role("button", name="Save").click()

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
