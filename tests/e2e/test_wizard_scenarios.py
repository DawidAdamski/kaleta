# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: What-if Scenarios.

Covers: KAL-WIF-001, KAL-WIF-002, KAL-WIF-003, KAL-WIF-004, KAL-WIF-005,
KAL-WIF-007
Page URL: /wizard/scenarios

The e2e instance shares one database across the session, so every test seeds
its own account and reads the figures for *that* account. The runway is the
one figure the app measures across the whole household by design, so the
tests that touch it assert the direction it moves, not its value.
"""

from __future__ import annotations

import datetime
import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e.seed_helpers import (
    seed_account,
    seed_category,
    seed_income_category,
    seed_reserve_fund,
    seed_transaction,
    update_account,
)

SCENARIOS_URL = "/wizard/scenarios"

#: The naive forecaster is quick, but the page runs its baseline on load and
#: again on every control change, and the e2e database is shared and busy.
_TIMEOUT = 60000

#: Enough distinct days for the forecaster (it needs 14) and for every
#: weekday to appear in the seasonal look-back.
_HISTORY_DAYS = 30

DELTAS_HEADING = "Scenario changes"


def _seed_flat_account(name: str, *, balance: str, daily: float = 100.0) -> int:
    """An account whose balance has gone nowhere for a month.

    Matched income and expense every day means a zero daily delta, so the
    naive forecaster projects a flat line at the account's balance with no
    confidence fan — which makes "stays positive" a fact rather than a hope.
    """
    account_id = seed_account(name)
    expense_id = seed_category(f"{name} Out")
    income_id = seed_income_category(f"{name} In")
    today = datetime.date.today()
    for offset in range(_HISTORY_DAYS):
        day = today - datetime.timedelta(days=offset)
        seed_transaction(account_id, expense_id, daily, date=day)
        seed_transaction(account_id, income_id, daily, tx_type="income", date=day)
    update_account(account_id, balance=balance)
    return account_id


def _choose(page: Page, label: str, option: str) -> None:
    page.locator(f'[aria-label="{label}"]').click()
    page.get_by_role("option", name=option, exact=True).click()


def _open(page: Page, base_url: str, account: str) -> None:
    """Open the panel and wait until its figures answer *this* account.

    The page opens on "All accounts" and re-runs when the select moves, so a
    verdict can be on screen and still belong to the previous selection. The
    chart card names the account it drew, which is what makes the wait exact.
    """
    page.goto(f"{base_url}{SCENARIOS_URL}")
    expect(page.get_by_text("What changes", exact=True)).to_be_visible(timeout=_TIMEOUT)
    _choose(page, "Account", account)
    expect(page.get_by_text(f"Baseline and scenario — {account}", exact=True)).to_be_visible(
        timeout=_TIMEOUT
    )


def _value(page: Page, key: str) -> str:
    return page.locator(f'[data-verdict="{key}"] .k-mono').inner_text()


def _pair(page: Page, key: str) -> tuple[float, float]:
    """The "before → after" figure, as two numbers."""
    before, after = _value(page, key).split("→")
    return _number(before), _number(after)


def _number(text: str) -> float:
    return float(text.replace(",", "").replace("\u00a0", "").strip())


def _deltas_card(page: Page) -> Locator:
    return page.locator(".q-card").filter(has_text=DELTAS_HEADING)


def _add_delta(
    page: Page,
    button: str,
    *,
    name: str,
    amount: str,
) -> None:
    """Open the builder for one delta kind, fill it in, and wait for the redraw.

    The delta list and the verdict are one refreshable, so the new row being
    on screen means the figures beside it already answer it.
    """
    page.get_by_role("button", name=button, exact=True).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=10000)
    dialog.get_by_role("textbox", name="Name").fill(name)
    dialog.get_by_role("textbox", name="Amount").fill(amount)
    dialog.get_by_role("button", name="Save", exact=True).click()
    expect(dialog).to_be_hidden(timeout=_TIMEOUT)
    expect(_deltas_card(page).get_by_text(name, exact=True)).to_be_visible(timeout=_TIMEOUT)


def _remove_delta(page: Page, name: str) -> None:
    card = _deltas_card(page)
    card.locator("div.row").filter(has_text=name).get_by_role("button").click()
    expect(card.get_by_text(name, exact=True)).to_have_count(0, timeout=_TIMEOUT)


# ---------------------------------------------------------------------------
# KAL-WIF-001 — an income drop shifts the projected balance
# ---------------------------------------------------------------------------


def test_income_drop_shifts_the_projected_balance(page: Page, base_url: str) -> None:
    """Covers: KAL-WIF-001"""
    account = "Scenario Income E2E"
    _seed_flat_account(account, balance="50000")

    _open(page, base_url, account)
    _add_delta(page, "Income change", name="Pay cut WIF E2E", amount="-30")

    before, after = _pair(page, "balance")
    assert after < before, (before, after)

    # A cut is money the account stops receiving, so the monthly figure is
    # negative — and it is read against this account's own income.
    assert _number(_value(page, "monthly_delta")) < 0


# ---------------------------------------------------------------------------
# KAL-WIF-002 — a one-off purchase shows the runway before and after
# ---------------------------------------------------------------------------


def test_one_off_purchase_shows_runway_before_and_after(page: Page, base_url: str) -> None:
    """Covers: KAL-WIF-002"""
    account = "Scenario Runway E2E"
    _seed_flat_account(account, balance="80000")

    fund_account = seed_account("Scenario Fund E2E")
    update_account(fund_account, balance="90000.00", type="savings")
    seed_reserve_fund("Scenario Emergency E2E", 120000.0, fund_account, kind="emergency")

    _open(page, base_url, account)
    _add_delta(page, "One-off amount", name="Car WIF E2E", amount="-50000")

    runway_before, runway_after = _pair(page, "runway")
    assert runway_after < runway_before, (runway_before, runway_after)


# ---------------------------------------------------------------------------
# KAL-WIF-003 — a new recurring expense moves the first-negative marker
# ---------------------------------------------------------------------------


def test_new_recurring_expense_moves_the_first_negative_marker(page: Page, base_url: str) -> None:
    """Covers: KAL-WIF-003

    30,000 flat over a twelve-month horizon survives anything smaller than
    2,500 a month. 4,000 a month runs it out inside the year, and the verdict
    has to say when.
    """
    account = "Scenario Negative E2E"
    _seed_flat_account(account, balance="30000")

    _open(page, base_url, account)
    expect(page.get_by_text("The balance stays positive across the whole horizon.")).to_be_visible(
        timeout=_TIMEOUT
    )

    _add_delta(page, "Recurring amount", name="New rent WIF E2E", amount="-4000")

    expect(
        page.get_by_text(re.compile(r"^The balance runs out on \d{4}-\d{2}-\d{2}"))
    ).to_be_visible(timeout=_TIMEOUT)


# ---------------------------------------------------------------------------
# KAL-WIF-004 — the panel works without the optional Prophet extra
# ---------------------------------------------------------------------------


def test_the_panel_works_without_prophet(page: Page, base_url: str) -> None:
    """Covers: KAL-WIF-004

    The e2e instance runs the dev dependencies, which do not include the
    optional ``prophet`` extra — so reaching a chart and a verdict here *is*
    the scenario, and nothing may ask for an install first.
    """
    from kaleta.services.forecasters import is_prophet_available

    assert not is_prophet_available(), "this scenario is about the extra being absent"

    account = "Scenario Naive E2E"
    _seed_flat_account(account, balance="20000")

    _open(page, base_url, account)

    expect(page.locator(".nicegui-echart").first).to_be_visible(timeout=_TIMEOUT)
    expect(page.locator('[data-verdict="balance"]')).to_be_visible()
    expect(page.get_by_text(re.compile("prophet", re.IGNORECASE))).to_have_count(0)


# ---------------------------------------------------------------------------
# KAL-WIF-005 — removing a change restores the baseline exactly
# ---------------------------------------------------------------------------


def test_removing_a_change_restores_the_baseline_exactly(page: Page, base_url: str) -> None:
    """Covers: KAL-WIF-005

    The literal 1000.00 is the scenario's, not the app's: a delta is added to
    the projection and to nothing else, so the difference is the amount typed.
    """
    account = "Scenario Restore E2E"
    _seed_flat_account(account, balance="40000")

    _open(page, base_url, account)
    baseline_before, baseline_after = _pair(page, "balance")
    assert baseline_before == baseline_after

    _add_delta(page, "One-off amount", name="Sofa WIF E2E", amount="-1000")

    before, after = _pair(page, "balance")
    assert before == baseline_before, "the baseline column never moves"
    assert round(before - after, 2) == 1000.00, (before, after)

    _remove_delta(page, "Sofa WIF E2E")

    before, after = _pair(page, "balance")
    assert before == baseline_before
    assert before == after


# ---------------------------------------------------------------------------
# KAL-WIF-007 — income cannot be cut by more than all of it
# ---------------------------------------------------------------------------


def test_income_cannot_be_cut_by_more_than_all_of_it(page: Page, base_url: str) -> None:
    """Covers: KAL-WIF-007

    The one shape rule a reader can break by typing, so it has to come back
    as a sentence rather than as the schema's English trace.
    """
    account = "Scenario Percent E2E"
    _seed_flat_account(account, balance="10000")

    _open(page, base_url, account)

    page.get_by_role("button", name="Income change", exact=True).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=10000)
    dialog.get_by_role("textbox", name="Name").fill("Impossible cut WIF E2E")
    dialog.get_by_role("textbox", name="Amount").fill("-150")
    dialog.get_by_role("button", name="Save", exact=True).click()

    expect(page.get_by_text("Income cannot fall by more than 100%.")).to_be_visible(timeout=10000)
    expect(dialog).to_be_visible()
    expect(_deltas_card(page).get_by_text("No changes yet.", exact=False)).to_be_visible()
