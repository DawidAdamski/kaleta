# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Quick Entry.

Covers: KAL-QIK-001, KAL-QIK-002, KAL-QIK-003

Keyboard-first entry in the add-transaction dialog: Enter saves from the
field being typed in, the last account and date are remembered, and "save
and add next" keeps the dialog open for a run of receipts.
Page URL: /transactions
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Locator, Page, expect

from tests.e2e.ledger import pick_open_menu_option, search_ledger
from tests.e2e.seed_helpers import list_transactions, seed_account, seed_category, seed_payee

PAYEE_LABEL = "Payee (optional)"


def _open_with_shortcut(page: Page) -> Locator:
    """Open the add dialog with Alt+N, the way a keyboard user does."""
    expect(page.locator(".q-table")).to_be_visible(timeout=10000)
    page.keyboard.press("Alt+n")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    return dialog


def _tab_until(page: Page, target: Locator, *, max_presses: int = 10) -> None:
    """Press Tab until focus lands inside ``target``."""
    for _ in range(max_presses):
        if target.evaluate("(el) => el.contains(document.activeElement)"):
            return
        page.keyboard.press("Tab")
    raise AssertionError("Tab never reached the target field")


def _pick_account(page: Page, dialog: Locator, account_name: str) -> None:
    dialog.get_by_label("Account", exact=True).click()
    pick_open_menu_option(page, account_name)


def _pick_category(page: Page, dialog: Locator, category_name: str) -> None:
    dialog.get_by_label("Category").click()
    pick_open_menu_option(page, category_name)


def _fill_amount(dialog: Locator, value: str) -> None:
    field = dialog.get_by_role("spinbutton", name="Amount", exact=True)
    field.click(click_count=3)
    field.fill(value)


def test_enter_saves_from_keyboard_only(page: Page, base_url: str) -> None:
    """Covers: KAL-QIK-001

    Alt+N opens the dialog with the amount focused, Tab moves between the
    fields, and Enter in the field being typed in saves — no mouse involved.
    """
    category_name = "Zzqik Klawiatura E2E"
    described = "Keyboard only Qik E2E"
    seed_account("Klawiatura Qik E2E")
    seed_category(category_name)

    page.goto(f"{base_url}/transactions")
    dialog = _open_with_shortcut(page)

    amount = dialog.get_by_role("spinbutton", name="Amount", exact=True)
    expect(amount).to_be_focused(timeout=5000)
    page.keyboard.type("23.45")

    page.keyboard.press("Tab")
    expect(dialog.get_by_label("Description (optional)")).to_be_focused()
    page.keyboard.type(described)

    category_field = dialog.get_by_label("Category").locator(
        "xpath=ancestor::*[contains(@class,'q-field')][1]"
    )
    _tab_until(page, category_field)
    page.keyboard.press("Enter")
    menu = page.locator(".q-menu").last
    expect(menu).to_be_visible(timeout=3000)
    page.keyboard.type("Zzqik")
    page.keyboard.press("Enter")
    expect(dialog.get_by_label("Category")).to_have_value(category_name, timeout=5000)

    _tab_until(page, dialog.get_by_label("Date", exact=True))
    page.keyboard.press("Enter")

    expect(dialog).to_be_hidden(timeout=5000)
    search_ledger(page, described)
    row = page.locator(".q-table tbody tr").filter(has_text=described)
    expect(row).to_have_count(1, timeout=5000)
    expect(row.get_by_text("-23.45")).to_be_visible()


def test_reopened_dialog_remembers_account_and_date(page: Page, base_url: str) -> None:
    """Covers: KAL-QIK-002

    Saving for "mBank" on 2026-07-05 preselects both the next time the form
    opens — including after a page reload, since the context is kept in the
    user's storage rather than in the page.
    """
    account_name = "mBank"
    category_name = "Zakupy Qik E2E"
    seed_account(account_name)
    seed_category(category_name)

    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    _pick_account(page, dialog, account_name)
    _fill_amount(dialog, "10.00")
    _pick_category(page, dialog, category_name)
    dialog.get_by_label("Date", exact=True).fill("2026-07-05")
    dialog.get_by_role("button", name="Save", exact=True).click()
    expect(dialog).to_be_hidden(timeout=5000)

    dialog = _open_with_shortcut(page)
    expect(dialog.get_by_label("Account", exact=True)).to_have_value(account_name)
    expect(dialog.get_by_label("Date", exact=True)).to_have_value("2026-07-05")
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden(timeout=5000)

    page.reload()
    dialog = _open_with_shortcut(page)
    expect(dialog.get_by_label("Account", exact=True)).to_have_value(account_name)
    expect(dialog.get_by_label("Date", exact=True)).to_have_value("2026-07-05")

    # The e2e browser shares one user storage across the suite; book one more
    # entry dated today so later tests do not inherit a July date.
    _fill_amount(dialog, "1.00")
    _pick_category(page, dialog, category_name)
    dialog.get_by_label("Date", exact=True).fill(datetime.date.today().isoformat())
    dialog.get_by_role("button", name="Save", exact=True).click()
    expect(dialog).to_be_hidden(timeout=5000)


def test_save_and_add_next_keeps_form_open(page: Page, base_url: str) -> None:
    """Covers: KAL-QIK-003

    "Save and add next" books the receipt, clears amount and payee, and keeps
    the dialog open with the account and date of the entry just saved.
    """
    account_name = "Paragony Qik E2E"
    category_name = "Spozywcze Qik E2E"
    payee_name = "Lidl Qik E2E"
    backlog_date = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    account_id = seed_account(account_name)
    seed_category(category_name)
    seed_payee(payee_name)

    page.goto(f"{base_url}/transactions?new=1")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    _pick_account(page, dialog, account_name)
    _fill_amount(dialog, "214.50")
    payee = dialog.get_by_label(PAYEE_LABEL)
    payee.click()
    payee.fill("Lidl Qik")
    pick_open_menu_option(page, payee_name)
    _pick_category(page, dialog, category_name)
    dialog.get_by_label("Date", exact=True).fill(backlog_date)
    dialog.get_by_role("button", name="Save and add next").click()

    expect(page.get_by_text("Transaction saved.").first).to_be_visible(timeout=5000)
    expect(dialog).to_be_visible()
    amount = dialog.get_by_role("spinbutton", name="Amount", exact=True)
    expect(amount).to_have_value("")
    expect(amount).to_be_focused()
    expect(dialog.get_by_label(PAYEE_LABEL)).to_have_value("")
    expect(dialog.get_by_label("Account", exact=True)).to_have_value(account_name)
    expect(dialog.get_by_label("Date", exact=True)).to_have_value(backlog_date)

    # The second receipt: the kept account and date go straight onto it, and
    # Ctrl+Enter is the keyboard form of the same button.
    page.keyboard.type("34.50")
    _pick_category(page, dialog, category_name)
    amount.press("Control+Enter")
    expect(amount).to_have_value("", timeout=5000)
    expect(dialog).to_be_visible()

    saved = list_transactions(account_id)
    assert sorted(tx["amount"] for tx in saved) == ["214.50", "34.50"]
    assert {tx["date"] for tx in saved} == {backlog_date}
