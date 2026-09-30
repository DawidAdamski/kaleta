# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Account Management — balances follow the ledger.

Page URL: /accounts
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Locator, Page, expect

from tests.e2e.seed_helpers import (
    get_or_seed_category,
    seed_account,
    seed_transaction,
    seed_transfer_pair,
    update_account,
)

# Balances count every row whatever its date. An old date keeps these rows off
# the first ledger page other tests read in the shared instance.
OLD_DAY = datetime.date(2020, 1, 15)


def _account_row(page: Page, name: str) -> Locator:
    return page.locator("div.border-b.py-2").filter(has=page.get_by_text(name, exact=True))


def _open_accounts(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/accounts")
    expect(page.get_by_text("Accounts", exact=True).first).to_be_visible(timeout=5000)


def test_balance_follows_income_and_expenses(page: Page, base_url: str) -> None:
    """Covers: KAL-ACC-005"""
    name = "PKO Main ACC5 E2E"
    account_id = seed_account(name)
    update_account(account_id, balance="1000.00")
    seed_transaction(account_id, get_or_seed_category("Jedzenie ACC E2E"), 200.00, date=OLD_DAY)
    seed_transaction(
        account_id,
        get_or_seed_category("Pensja ACC E2E", "income"),
        50.00,
        tx_type="income",
        date=OLD_DAY,
    )

    _open_accounts(page, base_url)
    expect(_account_row(page, name).get_by_text("850.00 PLN", exact=True)).to_be_visible(
        timeout=5000
    )


def test_a_transfer_moves_both_balances(page: Page, base_url: str) -> None:
    """Covers: KAL-ACC-006"""
    source, target = "PKO Main ACC6 E2E", "Oszczędności ACC6 E2E"
    source_id = seed_account(source)
    update_account(source_id, balance="1000.00")
    target_id = seed_account(target)
    seed_transfer_pair(
        source_id, target_id, get_or_seed_category("Jedzenie ACC E2E"), 500.00, "ACC6", date=OLD_DAY
    )

    _open_accounts(page, base_url)
    for name in (source, target):
        expect(_account_row(page, name).get_by_text("500.00 PLN", exact=True)).to_be_visible(
            timeout=5000
        )


def test_setting_the_current_balance_by_hand(page: Page, base_url: str) -> None:
    """Covers: KAL-ACC-008"""
    name = "PKO Main ACC8 E2E"
    account_id = seed_account(name)
    update_account(account_id, balance="1000.00")
    food = get_or_seed_category("Jedzenie ACC E2E")
    seed_transaction(account_id, food, 150.00, date=OLD_DAY)

    _open_accounts(page, base_url)
    row = _account_row(page, name)
    expect(row.get_by_text("850.00 PLN", exact=True)).to_be_visible(timeout=5000)

    row.get_by_role("button").filter(has_text="edit").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    balance = dialog.get_by_role("spinbutton", name="Balance", exact=True)
    balance.click(click_count=3)
    balance.fill("900.00")
    dialog.get_by_role("button", name="Save").click()

    expect(_account_row(page, name).get_by_text("900.00 PLN", exact=True)).to_be_visible(
        timeout=5000
    )

    seed_transaction(account_id, food, 100.00, date=OLD_DAY)
    _open_accounts(page, base_url)
    expect(_account_row(page, name).get_by_text("800.00 PLN", exact=True)).to_be_visible(
        timeout=5000
    )
