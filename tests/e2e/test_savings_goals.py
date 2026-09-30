# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Savings Goals (Skarbonki).

Page URL: /wizard/safety-funds?show=goals — goals are a filter of the funds
page. Account names start with "W" so they sort after the accounts other
tests pick from unscrolled menus in the shared instance.
"""

from __future__ import annotations

import datetime

from playwright.sync_api import Locator, Page, expect

from tests.e2e.ledger import pick_open_menu_option
from tests.e2e.seed_helpers import (
    get_account,
    seed_account,
    seed_reserve_fund,
    update_account,
)


def _goals(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/wizard/safety-funds?show=goals")
    expect(page.get_by_text("Safety & Reserve Funds", exact=True).first).to_be_visible(timeout=5000)


def _card(page: Page, name: str) -> Locator:
    return page.locator(".q-card").filter(has=page.get_by_text(name, exact=True))


def _fill_number(scope: Locator, label: str, value: str) -> None:
    field = scope.get_by_role("spinbutton", name=label, exact=True)
    field.click(click_count=3)
    field.fill(value)


def _eleven_whole_months_ahead(today: datetime.date) -> datetime.date:
    """A 1st of the month exactly 11 whole months from *today* (KAL-GOL-003).

    A month counts once its day comes round, so from any day but the 1st
    the 1st twelve months on is 11 whole months away.
    """
    months = 11 if today.day == 1 else 12
    total = today.year * 12 + today.month - 1 + months
    return datetime.date(total // 12, total % 12 + 1, 1)


def test_create_a_savings_goal(page: Page, base_url: str) -> None:
    """Covers: KAL-GOL-001"""
    vault = "Wakacje GOL1 E2E"
    seed_account(vault)

    _goals(page, base_url)
    page.get_by_role("button", name="Add goal").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_label("Name").fill("Holidays 2027 GOL1")
    _fill_number(dialog, "Target amount", "6000")
    dialog.get_by_label("Target date").fill("2027-06-01")
    dialog.locator(".q-select").filter(has_text="Backing account").click()
    pick_open_menu_option(page, vault)
    dialog.get_by_role("button", name="Save").click()

    card = _card(page, "Holidays 2027 GOL1")
    expect(card.get_by_text("0.00 / 6,000.00", exact=True)).to_be_visible(timeout=5000)
    expect(card.get_by_text("0%", exact=True)).to_be_visible(timeout=5000)


def test_contribute_and_see_the_pace(page: Page, base_url: str) -> None:
    """Covers: KAL-GOL-002, KAL-GOL-003"""
    source, vault = "Wypłaty GOL2 E2E", "Wakacje GOL2 E2E"
    source_id = seed_account(source)
    update_account(source_id, balance="1000.00")
    vault_id = seed_account(vault)
    by = _eleven_whole_months_ahead(datetime.date.today())
    seed_reserve_fund(
        "Holidays 2027 GOL2",
        6000.0,
        vault_id,
        kind="vacation",
        emergency_multiplier=None,
        target_date=by,
    )

    _goals(page, base_url)
    card = _card(page, "Holidays 2027 GOL2")
    card.get_by_role("button", name="Contribute").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)
    _fill_number(dialog, "Amount", "500")
    dialog.locator(".q-select").filter(has_text="From account").click()
    pick_open_menu_option(page, source)
    dialog.get_by_role("button", name="Contribute").click()

    card = _card(page, "Holidays 2027 GOL2")
    expect(card.get_by_text("500.00 / 6,000.00", exact=True)).to_be_visible(timeout=5000)
    expect(card.get_by_text("8%", exact=True)).to_be_visible(timeout=5000)
    expect(
        card.get_by_text(f"Save 500.00 a month to reach it by {by.isoformat()}", exact=True)
    ).to_be_visible(timeout=5000)
    assert get_account(source_id)["balance"] == "500.00"


def test_close_a_goal_and_release_the_money(page: Page, base_url: str) -> None:
    """Covers: KAL-GOL-004"""
    source, vault = "Wypłaty GOL4 E2E", "Wakacje GOL4 E2E"
    source_id = seed_account(source)
    update_account(source_id, balance="6000.00")
    vault_id = seed_account(vault)
    seed_reserve_fund(
        "Holidays 2027 GOL4", 6000.0, vault_id, kind="vacation", emergency_multiplier=None
    )

    _goals(page, base_url)
    card = _card(page, "Holidays 2027 GOL4")
    card.get_by_role("button", name="Contribute").click()
    dialog = page.get_by_role("dialog")
    _fill_number(dialog, "Amount", "6000")
    dialog.locator(".q-select").filter(has_text="From account").click()
    pick_open_menu_option(page, source)
    dialog.get_by_role("button", name="Contribute").click()
    expect(_card(page, "Holidays 2027 GOL4").get_by_text("100%", exact=True)).to_be_visible(
        timeout=5000
    )

    _card(page, "Holidays 2027 GOL4").locator("button").filter(has_text="check_circle").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Close Holidays 2027 GOL4?", exact=True)).to_be_visible(timeout=5000)
    # The dialog offers the account the money came from.
    expect(dialog.locator(".q-select").filter(has_text=source)).to_be_visible(timeout=5000)
    dialog.get_by_role("button", name="Close goal").click()

    expect(page.get_by_text("Archived funds", exact=True)).to_be_visible(timeout=5000)
    assert get_account(source_id)["balance"] == "6000.00"
    assert get_account(vault_id)["balance"] == "0.00"
