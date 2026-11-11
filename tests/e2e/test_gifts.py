# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Gift Planning — the yearly people-by-occasions grid.

Page URL: /wizard/gifts

Gift totals are sums over the whole family, so every test empties the grid
before and in a ``finally`` (rerun-safe, the shared-DB #19 lesson).
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import (
    clear_gifts,
    delete_reserve_fund,
    delete_transaction,
    gift_lane_ids,
    primary_irregular_fund_id,
    seed_account,
    seed_category,
    seed_gift,
    seed_reserve_fund,
    seed_transaction,
)


def _type_amount(page: Page, person: str, occasion: str, amount: str) -> None:
    """Type into one cell and commit it (Tab), as a user tabbing along a row."""
    field = page.get_by_role("spinbutton", name=f"{person}, {occasion}", exact=True)
    field.click()
    field.fill(amount)
    field.press("Tab")


def _add(page: Page, field_label: str, button: str, name: str) -> None:
    page.get_by_label(field_label, exact=True).fill(name)
    page.get_by_role("button", name=button, exact=True).click()


def test_maintain_the_gift_grid(page: Page, base_url: str) -> None:
    """Covers: KAL-GFT-001

    Mama — Birthday 200.00, Christmas 150.00; Tata — Christmas 100.00: rows
    350.00 and 100.00, the Christmas column 250.00, the year 450.00.
    """
    clear_gifts()
    try:
        page.goto(f"{base_url}/wizard/gifts")
        # A new grid starts with the default occasions as its columns.
        for occasion in ("Birthday", "Name day", "Christmas", "Easter", "St Nicholas' Day"):
            expect(page.get_by_role("columnheader").filter(has_text=occasion)).to_be_visible(
                timeout=10000
            )

        _add(page, "New person", "Add person", "Mama")
        expect(page.get_by_role("rowheader").filter(has_text="Mama")).to_be_visible(timeout=10000)
        _add(page, "New person", "Add person", "Tata")
        expect(page.get_by_role("rowheader").filter(has_text="Tata")).to_be_visible(timeout=10000)

        _type_amount(page, "Mama", "Birthday", "200")
        _type_amount(page, "Mama", "Christmas", "150")
        _type_amount(page, "Tata", "Christmas", "100")

        ids = gift_lane_ids()
        expect(page.get_by_test_id(f"gift-row-total-{ids['Mama']}")).to_have_text(
            "350.00", timeout=10000
        )
        expect(page.get_by_test_id(f"gift-row-total-{ids['Tata']}")).to_have_text("100.00")
        expect(page.get_by_test_id(f"gift-col-total-{ids['Christmas']}")).to_have_text("250.00")
        expect(page.get_by_test_id("gift-total")).to_have_text("450.00")
        expect(page.get_by_test_id("gift-grid-total")).to_have_text("450.00")

        # Saved, not just drawn: a fresh load reads the same total back.
        page.reload()
        expect(page.get_by_test_id("gift-total")).to_have_text("450.00", timeout=10000)
    finally:
        clear_gifts()


def test_gift_total_feeds_the_irregular_fund(page: Page, base_url: str) -> None:
    """Covers: KAL-GFT-002

    This year's grid (200.00 + 150.00 = 350.00) shows on the irregular fund
    page as a read-only "Gifts" line, on the primary (oldest live) fund.
    """
    clear_gifts()
    account_id = seed_account("Konto funduszu nieregularnego (e2e)")
    fund_id = seed_reserve_fund(
        "Wydatki nieregularne (e2e)", 0.0, account_id, kind="irregular", emergency_multiplier=None
    )
    try:
        seed_gift("Mum", "Birthday", 200)
        seed_gift("Mum", "Christmas", 150)
        primary_id = primary_irregular_fund_id()
        assert primary_id is not None

        page.goto(f"{base_url}/wizard/safety-funds/{primary_id}")
        gifts_row = page.get_by_test_id("irregular-derived-gifts")
        expect(gifts_row).to_be_visible(timeout=5000)
        expect(gifts_row.get_by_text("Gifts", exact=True)).to_be_visible()
        expect(gifts_row.get_by_text("350.00", exact=True)).to_be_visible()
    finally:
        clear_gifts()
        delete_reserve_fund(fund_id)


def test_mark_a_gift_as_bought(page: Page, base_url: str) -> None:
    """Covers: KAL-GFT-003

    A gift planned at 200.00, linked to a 189.99 expense in the ledger, is
    marked bought and shows that actual cost under its cell.
    """
    clear_gifts()
    account_id = seed_account("Konto (e2e gift bought)")
    category_id = seed_category("Prezenty e2e bought", "expense")
    tx_id = seed_transaction(account_id, category_id, 189.99, description="Prezent dla mamy e2e")
    cell_id = seed_gift("Mum", "Birthday", 200)
    try:
        page.goto(f"{base_url}/wizard/gifts")
        page.get_by_role("button", name="Options: Mum, Birthday", exact=True).click()
        page.locator(".q-menu").get_by_text("Mark as bought", exact=True).click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible(timeout=5000)
        dialog.get_by_label("Transaction", exact=True).click()
        page.get_by_role("option").filter(has_text="Prezent dla mamy e2e").first.click()
        dialog.get_by_role("button", name="Link").click()

        expect(page.get_by_test_id(f"gift-bought-{cell_id}")).to_have_text(
            "Bought 189.99", timeout=10000
        )
        # The planned amount is untouched.
        expect(page.get_by_role("spinbutton", name="Mum, Birthday", exact=True)).to_have_value(
            "200.00"
        )
    finally:
        clear_gifts()
        delete_transaction(tx_id)


def test_a_new_year_starts_as_a_copy_of_the_last(page: Page, base_url: str) -> None:
    """Covers: KAL-GFT-004

    A far-future pair of years, so no other test's grid is in either of them.
    """
    source, target = 2041, 2042
    clear_gifts()
    try:
        seed_gift("Mama", "Birthday", 200, year=source)
        seed_gift("Mama", "Christmas", 150, year=source)
        seed_gift("Tata", "Christmas", 100, year=source)

        page.goto(f"{base_url}/wizard/gifts?year={target}")
        expect(page.get_by_text(f"Nothing planned for {target} yet.")).to_be_visible(timeout=10000)
        page.get_by_role("button", name=f"Copy from {source}").click()
        expect(page.get_by_test_id("gift-total")).to_have_text("450.00", timeout=10000)
        expect(page.get_by_text(f"Nothing planned for {target} yet.")).to_have_count(0)
    finally:
        clear_gifts()


def test_adding_an_occasion_adds_an_empty_column(page: Page, base_url: str) -> None:
    """Covers: KAL-GFT-005"""
    clear_gifts()
    try:
        seed_gift("Mama", "Birthday", 200)
        page.goto(f"{base_url}/wizard/gifts")
        expect(page.get_by_test_id("gift-total")).to_have_text("200.00", timeout=10000)

        _add(page, "New occasion", "Add occasion", "Rocznica ślubu")
        expect(page.get_by_role("columnheader").filter(has_text="Rocznica ślubu")).to_be_visible(
            timeout=10000
        )
        ids = gift_lane_ids()
        expect(page.get_by_test_id(f"gift-col-total-{ids['Rocznica ślubu']}")).to_have_text("0.00")
        expect(page.get_by_test_id("gift-total")).to_have_text("200.00")
        expect(
            page.get_by_role("spinbutton", name="Mama, Rocznica ślubu", exact=True)
        ).to_have_value("")
    finally:
        clear_gifts()


def test_the_year_switcher_moves_between_grids(page: Page, base_url: str) -> None:
    """Covers: KAL-GFT-004"""
    this_year = datetime.date.today().year
    clear_gifts()
    try:
        seed_gift("Mama", "Birthday", 200)
        page.goto(f"{base_url}/wizard/gifts")
        expect(page.get_by_text(f"Gifts in {this_year}", exact=True)).to_be_visible(timeout=10000)
        page.get_by_role("button", name="Next year").click()
        expect(page.get_by_text(f"Gifts in {this_year + 1}", exact=True)).to_be_visible(
            timeout=10000
        )
        expect(page.get_by_test_id("gift-total")).to_have_text("0.00")
        expect(page.get_by_role("button", name=f"Copy from {this_year}")).to_be_visible()
    finally:
        clear_gifts()
