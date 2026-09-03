# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Manual Transaction Entry.

Covers: KAL-TXN-001

Maps the q3-test-safety-net flow: add, edit, and split a transaction.
Page URL: /transactions
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_category, seed_transaction


def _fill_number(scope: Page, label: str, value: str) -> None:
    field = scope.get_by_role("spinbutton", name=label, exact=True)
    field.click(click_count=3)
    field.fill(value)


def _select_option(page: Page, dialog: Page, select_index: int, option: str) -> None:
    """Open a Quasar select and pick an option, scrolling virtual lists if needed."""
    dialog.locator(".q-select").nth(select_index).click()
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
