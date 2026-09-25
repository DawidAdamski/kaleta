# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Payee Identities.

Page URLs: /payees (merge suggestions), /reports/top-merchants (Top payees by spend).
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    get_or_seed_payee,
    get_transaction,
    list_payees,
    seed_account,
    seed_category,
    seed_payee,
    seed_transaction,
)

SUGGESTION = "[data-merge-suggestion]"


def test_top_payees_report_ranks_by_spend(page: Page, base_url: str) -> None:
    """Covers: KAL-PID-003

    Given transactions across several payees exist, the Top Merchants report
    ranks payees by total amount spent in the selected period.
    """
    account_id = seed_account("PID Report E2E")
    category_id = seed_category("PID Food E2E")
    kaufland_id = seed_payee("Kaufland PID E2E")
    biedronka_id = seed_payee("Biedronka PID E2E")

    today = datetime.date.today()
    seed_transaction(
        account_id,
        category_id,
        200.0,
        date=today,
        payee_id=kaufland_id,
        description="Kaufland shop",
    )
    seed_transaction(
        account_id,
        category_id,
        75.0,
        date=today,
        payee_id=biedronka_id,
        description="Biedronka shop",
    )
    seed_transaction(
        account_id,
        category_id,
        50.0,
        date=today,
        payee_id=biedronka_id,
        description="Biedronka shop 2",
    )

    page.goto(f"{base_url}/reports/top-merchants")
    expect(page.get_by_text("Top Merchants", exact=True).first).to_be_visible(timeout=5000)

    table = page.locator(".q-table")
    expect(table.get_by_text("Kaufland PID E2E", exact=True)).to_be_visible(timeout=5000)
    expect(table.get_by_text("Biedronka PID E2E", exact=True)).to_be_visible(timeout=5000)

    kaufland_row = table.locator("tbody tr").filter(has_text="Kaufland PID E2E")
    biedronka_row = table.locator("tbody tr").filter(has_text="Biedronka PID E2E")
    expect(kaufland_row).to_be_visible()
    expect(biedronka_row).to_be_visible()

    kaufland_index = kaufland_row.evaluate(
        "el => Array.from(el.parentElement.children).indexOf(el)"
    )
    biedronka_index = biedronka_row.evaluate(
        "el => Array.from(el.parentElement.children).indexOf(el)"
    )
    assert kaufland_index < biedronka_index, (
        "Higher-spend payee should appear above lower-spend payee"
    )


def test_payees_page_suggests_merging_look_alike_payees(page: Page, base_url: str) -> None:
    """Covers: KAL-PID-001

    Given payees "LIDL SP. Z O.O." and "Lidl 1234 Warszawa" exist, the Payees
    page shows one merge suggestion grouping the two.
    """
    get_or_seed_payee("LIDL SP. Z O.O.")
    get_or_seed_payee("Lidl 1234 Warszawa")

    page.goto(f"{base_url}/payees")

    suggestion = page.locator(SUGGESTION).filter(has_text="LIDL SP. Z O.O.")
    expect(suggestion).to_have_count(1, timeout=5000)
    expect(suggestion.get_by_text("LIDL SP. Z O.O.", exact=True)).to_be_visible()
    expect(suggestion.get_by_text("Lidl 1234 Warszawa", exact=True)).to_be_visible()


def test_accepting_merge_suggestion_under_new_name(page: Page, base_url: str) -> None:
    """Covers: KAL-PID-002

    Accepting the suggestion for "LIDL SP. Z O.O." and "Lidl 1234 Warszawa"
    with the name "Lidl" moves both payees' transactions to "Lidl" and
    removes the duplicates.
    """
    account_id = seed_account("PID Merge E2E")
    category_id = seed_category("PID Merge Food E2E")
    spolka_id = get_or_seed_payee("LIDL SP. Z O.O.")
    sklep_id = get_or_seed_payee("Lidl 1234 Warszawa")
    tx_ids = [
        seed_transaction(account_id, category_id, 30.0, payee_id=spolka_id, description="Zakupy"),
        seed_transaction(account_id, category_id, 45.0, payee_id=sklep_id, description="Zakupy"),
    ]

    page.goto(f"{base_url}/payees")
    suggestion = page.locator(SUGGESTION).filter(has_text="LIDL SP. Z O.O.")
    expect(suggestion).to_have_count(1, timeout=5000)
    suggestion.get_by_label("New name (optional)").fill("Lidl")
    suggestion.get_by_role("button", name="Merge").click()
    page.locator(".q-dialog").get_by_role("button", name="Merge").click()

    expect(page.locator(SUGGESTION).filter(has_text="LIDL SP. Z O.O.")).to_have_count(
        0, timeout=5000
    )
    expect(page.locator(".q-table").get_by_text("Lidl", exact=True)).to_be_visible()

    names_by_id = {p["id"]: p["name"] for p in list_payees()}
    assert "LIDL SP. Z O.O." not in names_by_id.values()
    assert "Lidl 1234 Warszawa" not in names_by_id.values()
    for tx_id in tx_ids:
        assert names_by_id[get_transaction(tx_id)["payee_id"]] == "Lidl"
