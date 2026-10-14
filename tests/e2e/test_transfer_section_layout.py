# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E test: the transfer-suggestions list is capped and accept-all stays put.

Covers: KAL-CSV-037
Page URL: /import (Confirm step)
"""

from __future__ import annotations

import datetime
from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.ledger import pick_open_menu_option
from tests.e2e.seed_helpers import (
    seed_account,
    seed_category,
    seed_income_category,
    seed_transaction,
)

PAIRS_CSV = Path(__file__).resolve().parent / "fixtures" / "mbank_transfer_pairs.csv"


def _account_option(name: str, currency: str = "PLN") -> str:
    return f"{name} ({currency})"


def _pick_import_option(page: Page, label: str, option: str) -> None:
    page.keyboard.press("Escape")
    page.locator(".q-select").filter(has_text=label).click()
    pick_open_menu_option(page, option)


def _step(page: Page, step: int) -> None:
    page.keyboard.press("Escape")
    page.locator(f'[data-step="{step}"]').click()
    expect(page.locator(f'[data-step-panel="{step}"]')).to_be_visible(timeout=5000)


def test_transfer_list_is_capped_and_accept_all_stays_in_the_footer(
    page: Page, base_url: str
) -> None:
    """Covers: KAL-CSV-037

    A long run of transfer suggestions used to grow the card until the
    accept-all control was pushed off-screen. The pair list now scrolls inside
    a capped box, and accept-all sits in a footer under it — reachable however
    many pairs there are.
    """
    mbank_name = "mBank TRF-037 E2E"
    pko_name = "PKO BP TRF-037 E2E"
    expense_cat = "AAA TRF-037 Expense"
    income_cat = "AAA TRF-037 Income"
    seed_account(mbank_name)
    pko = seed_account(pko_name)
    seed_category(expense_cat)
    income_cat_id = seed_income_category(income_cat)
    # Counterpart legs already on PKO, within 2 days of the file's rows.
    seed_transaction(
        pko,
        income_cat_id,
        517.23,
        tx_type="income",
        date=datetime.date(2019, 3, 13),
        description="Z mBanku TRF-037 E2E",
    )
    seed_transaction(
        pko,
        income_cat_id,
        123.45,
        tx_type="income",
        date=datetime.date(2019, 3, 15),
        description="Zwrot TRF-037 E2E",
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
    expect(confirm.locator("[data-transfer-section]")).to_be_visible(timeout=10000)
    expect(confirm.locator("[data-transfer-pair]").first).to_be_visible(timeout=10000)

    # The list scrolls inside a bounded box: a capped max-height and a
    # scrollable overflow, so it cannot grow the card without limit.
    pairs = confirm.locator("[data-transfer-pairs]")
    max_height = pairs.evaluate("el => getComputedStyle(el).maxHeight")
    overflow_y = pairs.evaluate("el => getComputedStyle(el).overflowY")
    assert max_height not in ("none", ""), max_height
    assert overflow_y in ("auto", "scroll"), overflow_y

    # Accept-all sits in the pinned footer, not loose at the end of the list.
    footer_accept_all = confirm.locator(".k-card-footer [data-transfer-accept-all]")
    expect(footer_accept_all).to_be_visible()
    expect(footer_accept_all).to_have_count(1)
