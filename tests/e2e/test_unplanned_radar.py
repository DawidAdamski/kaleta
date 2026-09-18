# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for the unplanned expenses radar (Feature: Recurring Payment Detection).

Page URL: /wizard/unplanned-radar

The e2e instance shares one database across the whole session, so every test
seeds uniquely named payees and scopes its assertions to that payee's row.
"""

from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e.seed_helpers import (
    list_planned_transactions,
    seed_account,
    seed_category,
    seed_irregular_charges,
    seed_recurring_payee_charges,
)

# (days_ago, amount) — a yearly car service that drifted 1200 → 1400.
CAR_SERVICE_CHARGES = [(730, 1200.00), (365, 1400.00)]
RADAR_URL = "/wizard/unplanned-radar"
CANDIDATES_HEADING = "Detected irregular costs"
PLANNED_HEADING = "Planned with linked history"


def _open_radar(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}{RADAR_URL}")
    expect(page.get_by_text(CANDIDATES_HEADING, exact=True)).to_be_visible(timeout=10000)


def _card(page: Page, heading: str) -> Locator:
    return page.locator(".q-card").filter(has_text=heading)


def _row(card: Locator, name: str) -> Locator:
    """The one list row inside *card* that names *name*."""
    return card.locator("div.row").filter(has_text=name)


def test_irregular_repeat_cost_is_detected(page: Page, base_url: str) -> None:
    """Covers: KAL-REC-005

    Two charges a year apart, drifting in amount, surface as a radar candidate
    with the median amount and a yearly rhythm.
    """
    account_id = seed_account("Radar Detect E2E")
    category_id = seed_category("Radar Car E2E")
    seed_irregular_charges(account_id, category_id, "Serwis Auto E2E", CAR_SERVICE_CHARGES)

    _open_radar(page, base_url)

    row = _row(_card(page, CANDIDATES_HEADING), "Serwis Auto E2E")
    expect(row).to_have_count(1)
    expect(row.get_by_text(re.compile(r"^Charges: 2, last on "))).to_be_visible(timeout=10000)
    expect(row.get_by_text("1,300.00", exact=True)).to_be_visible(timeout=5000)
    expect(row.get_by_text("Yearly", exact=True)).to_be_visible(timeout=5000)


def test_monthly_charges_stay_out_of_the_radar(page: Page, base_url: str) -> None:
    """Covers: KAL-REC-006

    A monthly rhythm belongs to the Subscriptions tracker, not the radar.
    """
    account_id = seed_account("Radar Monthly E2E")
    category_id = seed_category("Radar Cinema E2E")
    seed_recurring_payee_charges(account_id, category_id, "Kino Helios E2E", 49.99, months=3)

    _open_radar(page, base_url)

    expect(_card(page, CANDIDATES_HEADING).get_by_text("Kino Helios E2E")).to_have_count(0)


def test_plan_an_irregular_cost_from_the_radar(page: Page, base_url: str) -> None:
    """Covers: KAL-REC-007

    "Plan it" opens a pre-filled dialog; saving creates the planned transaction
    and retires the candidate.
    """
    account_id = seed_account("Radar Plan E2E")
    category_id = seed_category("Radar Plan Car E2E")
    seed_irregular_charges(account_id, category_id, "Serwis Plan E2E", CAR_SERVICE_CHARGES)

    _open_radar(page, base_url)

    row = _row(_card(page, CANDIDATES_HEADING), "Serwis Plan E2E")
    expect(row).to_have_count(1)
    row.get_by_role("button", name="Plan it").click()

    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Plan this cost", exact=True)).to_be_visible(timeout=5000)
    expect(dialog.get_by_text("Repeats: Yearly", exact=True)).to_be_visible(timeout=5000)
    dialog.get_by_role("button", name="Plan it").click()

    planned_row = _row(_card(page, PLANNED_HEADING), "Serwis Plan E2E")
    expect(planned_row).to_have_count(1, timeout=10000)

    saved = [pt for pt in list_planned_transactions() if pt["name"] == "Serwis Plan E2E"]
    assert len(saved) == 1, saved
    assert saved[0]["amount"] == "1300.00"
    assert saved[0]["frequency"] == "yearly"
    assert saved[0]["interval"] == 1
    assert saved[0]["account_id"] == account_id
    assert saved[0]["category_id"] == category_id

    expect(_row(_card(page, CANDIDATES_HEADING), "Serwis Plan E2E")).to_have_count(0)


def test_planned_transaction_keeps_its_source_payments(page: Page, base_url: str) -> None:
    """Covers: KAL-REC-003

    A plan built from a detection lists the historical payments it came from.
    """
    account_id = seed_account("Radar Link E2E")
    category_id = seed_category("Radar Link Car E2E")
    seed_irregular_charges(account_id, category_id, "Serwis Link E2E", CAR_SERVICE_CHARGES)

    _open_radar(page, base_url)

    _row(_card(page, CANDIDATES_HEADING), "Serwis Link E2E").get_by_role(
        "button", name="Plan it"
    ).click()
    page.get_by_role("dialog").get_by_role("button", name="Plan it").click()

    planned_row = _row(_card(page, PLANNED_HEADING), "Serwis Link E2E")
    expect(planned_row).to_have_count(1, timeout=10000)
    expect(planned_row.get_by_text("Past payments linked: 2", exact=True)).to_be_visible(
        timeout=5000
    )


def test_dismissed_candidate_does_not_come_back(page: Page, base_url: str) -> None:
    """Covers: KAL-REC-008

    "Not a repeating cost" is persisted, so reopening the page does not
    resurface it.
    """
    account_id = seed_account("Radar Dismiss E2E")
    category_id = seed_category("Radar Dismiss Car E2E")
    seed_irregular_charges(account_id, category_id, "Serwis Dismiss E2E", CAR_SERVICE_CHARGES)

    _open_radar(page, base_url)

    row = _row(_card(page, CANDIDATES_HEADING), "Serwis Dismiss E2E")
    expect(row).to_have_count(1)
    # Dismissing reloads the page itself — let that navigation finish before
    # driving a fresh one, or the goto below races it into ERR_ABORTED.
    with page.expect_navigation(wait_until="load", timeout=15000):
        row.get_by_role("button", name="Not a repeating cost").click()

    _open_radar(page, base_url)
    expect(_row(_card(page, CANDIDATES_HEADING), "Serwis Dismiss E2E")).to_have_count(0)


def test_radar_offers_the_irregular_fund_link(page: Page, base_url: str) -> None:
    """Covers: KAL-REC-009

    The fund line rolls the yearly estimates up and points at Safety &
    Reserve Funds. The 1450.00 total itself is asserted in
    ``tests/integration/test_unplanned_radar_summary.py``, where the database
    holds only the two scenario costs.
    """
    account_id = seed_account("Radar Fund E2E")
    category_id = seed_category("Radar Fund Car E2E")
    seed_irregular_charges(
        account_id, category_id, "Serwis Fund E2E", [(730, 1300.00), (365, 1300.00)]
    )
    seed_irregular_charges(
        account_id, category_id, "Kominiarz Fund E2E", [(730, 150.00), (365, 150.00)]
    )

    _open_radar(page, base_url)

    fund_card = _card(page, "Irregular expenses fund")
    expect(fund_card.get_by_text(re.compile(r"^Irregular costs: \d+ — about "))).to_be_visible(
        timeout=10000
    )
    expect(fund_card.get_by_role("button", name="Open Safety & Reserve Funds")).to_be_visible(
        timeout=5000
    )
    fund_card.get_by_role("button", name="Open Safety & Reserve Funds").click()
    expect(page).to_have_url(re.compile(r"/wizard/safety-funds$"), timeout=10000)
