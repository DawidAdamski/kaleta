# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Account Balance Forecast.

Maps scenarios from docs/bdd.md — Feature: Account Balance Forecast.
Covers: KAL-FCT-001, KAL-FCT-002, KAL-FCT-003, KAL-FCT-007, KAL-FCT-010,
KAL-FCT-011
Page URL: /forecast
"""

from __future__ import annotations

import datetime

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_category, seed_many_transactions

#: Prophet is slow when installed; the naive projection is not. Either way the
#: page answers on its own, so the wait is for an answer, not for a click.
_RUN_TIMEOUT = 60000


def _answered(page: Page):
    """The page has finished: either four figures, or a reason there are none."""
    return page.get_by_text("Balance today").or_(
        page.get_by_text("Insufficient transaction history for forecasting.")
    )


def _control(page: Page, label: str):
    """The select named by its aria-label — Quasar puts it on the control div."""
    return page.locator(f'[aria-label="{label}"]')


def _kpi(page: Page, key: str):
    """One of the four figures, by name rather than by its title text."""
    return page.locator(f'[data-kpi="{key}"] .k-mono').first


def _figure(page: Page, key: str) -> float:
    """The figure as a number — "+1,234.56 zł" is prose until it is parsed."""
    text = _kpi(page, key).inner_text()
    return float(text.replace("zł", "").replace(",", "").replace("±", "").replace(" ", ""))


def _choose(page: Page, label: str, option: str) -> None:
    _control(page, label).click()
    page.get_by_role("option", name=option, exact=True).click()


# ---------------------------------------------------------------------------
# Scenario: the page runs its own baseline on load
# ---------------------------------------------------------------------------


def test_the_forecast_runs_without_being_asked(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-010

    The page used to open as an empty frame behind a Run button — a question
    the user had already answered by navigating here.
    """
    acc_id = seed_account("PKO Forecast OnLoad E2E")
    cat_id = seed_category("Forecast OnLoad Cat E2E")
    seed_many_transactions(acc_id, cat_id, n_days=90)

    page.goto(f"{base_url}/forecast")

    expect(page.get_by_text("Balance Forecast", exact=True)).to_be_visible(timeout=5000)
    # Nothing is clicked between the goto above and this assertion.
    expect(_answered(page)).to_be_visible(timeout=_RUN_TIMEOUT)

    # And the button is there for afterwards, as a re-run rather than a run.
    expect(page.get_by_role("button", name="Re-run")).to_be_visible()


def test_the_four_figures_stand_above_the_chart(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-010"""
    acc_id = seed_account("PKO Forecast Kpis E2E")
    cat_id = seed_category("Forecast Kpis Cat E2E")
    seed_many_transactions(acc_id, cat_id, n_days=120)

    page.goto(f"{base_url}/forecast")
    _choose(page, "Account", "PKO Forecast Kpis E2E")

    expect(page.get_by_text("Balance today")).to_be_visible(timeout=_RUN_TIMEOUT)
    for figure in ("Predicted", "Change", "Confidence"):
        expect(page.get_by_text(figure, exact=True).first).to_be_visible(timeout=5000)

    # The chart is under them, not behind a button.
    expect(page.locator(".echarts, .nicegui-echart").first).to_be_visible(timeout=10000)


# ---------------------------------------------------------------------------
# Scenario: Run a 30-day forecast for a single account
# ---------------------------------------------------------------------------


def test_run_30_day_forecast_single_account(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-001"""
    acc_id = seed_account("PKO Forecast 30d E2E")
    cat_id = seed_category("Forecast Expense 30d E2E")
    seed_many_transactions(acc_id, cat_id, n_days=90)

    page.goto(f"{base_url}/forecast")
    _choose(page, "Account", "PKO Forecast 30d E2E")
    _choose(page, "Forecast horizon (days)", "30 days")

    expect(_answered(page)).to_be_visible(timeout=_RUN_TIMEOUT)


# ---------------------------------------------------------------------------
# Scenario: Run a 90-day forecast
# ---------------------------------------------------------------------------


def test_run_90_day_forecast(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-002"""
    acc_id = seed_account("PKO Forecast 90d E2E")
    cat_id = seed_category("Forecast Expense 90d E2E")
    seed_many_transactions(acc_id, cat_id, n_days=90)

    page.goto(f"{base_url}/forecast")
    _choose(page, "Account", "PKO Forecast 90d E2E")
    _choose(page, "Forecast horizon (days)", "90 days")

    expect(_answered(page)).to_be_visible(timeout=_RUN_TIMEOUT)


# ---------------------------------------------------------------------------
# Scenario: Run a forecast for All accounts combined
# ---------------------------------------------------------------------------


def test_run_forecast_all_accounts(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-003"""
    page.goto(f"{base_url}/forecast")

    # Chosen, not assumed: the page remembers the last account across visits
    # (that is what `forecast_account` is for), so "All Accounts" is the
    # default only until someone picks something else.
    _choose(page, "Account", "All Accounts")

    expect(_control(page, "Account")).to_contain_text("All Accounts", timeout=5000)
    expect(_answered(page)).to_be_visible(timeout=_RUN_TIMEOUT)


# ---------------------------------------------------------------------------
# Scenario: Warning shown when history is insufficient
# ---------------------------------------------------------------------------


def test_warning_shown_for_insufficient_history(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-007"""
    acc_id = seed_account("New Acct Forecast Insuf E2E")
    cat_id = seed_category("Forecast Insuf Cat E2E")
    seed_many_transactions(acc_id, cat_id, n_days=7)

    page.goto(f"{base_url}/forecast")
    _choose(page, "Account", "New Acct Forecast Insuf E2E")

    expect(page.get_by_text("Insufficient transaction history for forecasting.")).to_be_visible(
        timeout=_RUN_TIMEOUT
    )
    # And no chart is displayed — the figures go with it.
    expect(page.get_by_text("Balance today")).to_have_count(0)


# ---------------------------------------------------------------------------
# Scenario: the figures include the scenario shifts the chart draws
# ---------------------------------------------------------------------------


def test_a_scenario_moves_the_predicted_figure(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-011

    The figures are read off the same series the chart is drawn from, so a
    what-if that lifts the line lifts them by exactly as much. The prototype
    recomputed them from the raw forecast, and they disagreed with the
    picture beside them.
    """
    acc_id = seed_account("PKO Forecast Scenario E2E")
    cat_id = seed_category("Forecast Scenario Cat E2E")
    seed_many_transactions(acc_id, cat_id, n_days=120)

    page.goto(f"{base_url}/forecast")
    _choose(page, "Account", "PKO Forecast Scenario E2E")
    _choose(page, "Forecast horizon (days)", "60 days")
    expect(_kpi(page, "predicted")).to_be_visible(timeout=_RUN_TIMEOUT)

    before_predicted = _figure(page, "predicted")
    before_change = _figure(page, "change")
    before_text = _kpi(page, "predicted").inner_text()

    # A windfall a week from now, well inside a 60-day horizon.
    when = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    page.get_by_text("Add scenario", exact=True).click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Label").fill("Bonus E2E")
    dialog.locator('input[type="date"]').fill(when)
    dialog.get_by_label("Amount (zł; negative for expenses)").fill("10000")
    dialog.get_by_role("button", name="Save").click()

    expect(_kpi(page, "predicted")).not_to_have_text(before_text, timeout=_RUN_TIMEOUT)
    assert _figure(page, "predicted") == pytest.approx(before_predicted + 10000, abs=0.01)
    assert _figure(page, "change") == pytest.approx(before_change + 10000, abs=0.01)

    # Take it away again — both so the figure comes back, and so the scenario
    # does not follow the session into the next test.
    page.locator('[aria-label="Remove scenario Bonus E2E"]').click()
    expect(_kpi(page, "predicted")).to_have_text(before_text, timeout=_RUN_TIMEOUT)
