# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Account Balance Forecast.

Maps scenarios from docs/bdd.md — Feature: Account Balance Forecast.
Covers: KAL-FCT-001, KAL-FCT-002, KAL-FCT-003, KAL-FCT-007, KAL-FCT-010,
KAL-FCT-011, KAL-FCT-013
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

#: For what does not need a forecaster at all — a scenario shifting a result
#: already in hand. Short on purpose: if this ever starts a run again, the
#: test should notice rather than wait it out.
_REDRAW_TIMEOUT = 5000


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
    seed_many_transactions(acc_id, cat_id, n_days=120)

    # Chosen on a first visit, so the account is this test's own and the page
    # is remembered as such. Nothing is clicked after the reload below.
    page.goto(f"{base_url}/forecast")
    _choose(page, "Account", "PKO Forecast OnLoad E2E")
    expect(_kpi(page, "predicted")).to_be_visible(timeout=_RUN_TIMEOUT)

    page.reload()

    # A chart and its four figures, with no click between the reload and here.
    for key in ("balance_today", "predicted", "change", "confidence"):
        expect(_kpi(page, key)).to_be_visible(timeout=_RUN_TIMEOUT)
    expect(page.locator(".nicegui-echart").first).to_be_visible(timeout=10000)

    # And the button is there for afterwards, as a re-run rather than a run.
    expect(page.get_by_role("button", name="Re-run")).to_be_visible()


def test_the_four_figures_stand_above_the_chart(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-010"""
    acc_id = seed_account("PKO Forecast Kpis E2E")
    cat_id = seed_category("Forecast Kpis Cat E2E")
    seed_many_transactions(acc_id, cat_id, n_days=120)

    page.goto(f"{base_url}/forecast")
    _choose(page, "Account", "PKO Forecast Kpis E2E")

    # By `data-kpi`, not by title text: "Predicted", "Change" and
    # "Confidence" all appear again in the legend and the table below.
    for key in ("balance_today", "predicted", "change", "confidence"):
        expect(_kpi(page, key)).to_be_visible(timeout=_RUN_TIMEOUT)

    chart = page.locator(".nicegui-echart").first
    expect(chart).to_be_visible(timeout=10000)

    # Above the chart, which is what "above" means.
    figures = page.locator('[data-kpi="predicted"]').first.bounding_box()
    chart_box = chart.bounding_box()
    assert figures is not None and chart_box is not None
    assert figures["y"] + figures["height"] <= chart_box["y"], (figures, chart_box)


# ---------------------------------------------------------------------------
# Scenario: Run a 30-day forecast for a single account
# ---------------------------------------------------------------------------


def test_run_30_day_forecast_single_account(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-001"""
    acc_id = seed_account("PKO Forecast 30d E2E")
    cat_id = seed_category("Forecast Expense 30d E2E")
    seed_many_transactions(acc_id, cat_id, n_days=120)

    page.goto(f"{base_url}/forecast")
    _choose(page, "Account", "PKO Forecast 30d E2E")
    _choose(page, "Forecast horizon (days)", "30 days")

    # The scenario asks for a chart and a predicted balance, so the test asks
    # for those and not for "either that or a warning".
    expect(_kpi(page, "predicted")).to_be_visible(timeout=_RUN_TIMEOUT)
    expect(_kpi(page, "confidence")).to_be_visible()
    expect(page.locator(".nicegui-echart").first).to_be_visible(timeout=10000)


# ---------------------------------------------------------------------------
# Scenario: Run a 90-day forecast
# ---------------------------------------------------------------------------


def test_run_90_day_forecast(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-002"""
    acc_id = seed_account("PKO Forecast 90d E2E")
    cat_id = seed_category("Forecast Expense 90d E2E")
    seed_many_transactions(acc_id, cat_id, n_days=120)

    page.goto(f"{base_url}/forecast")
    _choose(page, "Account", "PKO Forecast 90d E2E")
    _choose(page, "Forecast horizon (days)", "90 days")

    expect(_kpi(page, "predicted")).to_be_visible(timeout=_RUN_TIMEOUT)
    # "Extends 90 days beyond today" — the horizon the figure is dated at.
    # The forecast runs from the day after the last *transaction*, and
    # `seed_many_transactions` posts one today, so here that is today + 90.
    horizon = (datetime.date.today() + datetime.timedelta(days=90)).strftime("%d.%m.%Y")
    expect(page.locator('[data-kpi="predicted"]')).to_contain_text(horizon, timeout=10000)


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

    # Every account's history at once is more than enough to forecast, so
    # this asserts the figures rather than "those or a warning" — all four of
    # them, which is what the scenario claims.
    for key in ("balance_today", "predicted", "change", "confidence"):
        expect(_kpi(page, key)).to_be_visible(timeout=_RUN_TIMEOUT)
    # And the chart they stand above names the selection they belong to.
    # (The select's own value says the same thing, which is why that is not
    # what this asserts.)
    expect(page.get_by_text("Balance forecast — All Accounts")).to_be_visible(timeout=10000)
    expect(page.locator(".nicegui-echart").first).to_be_visible(timeout=10000)


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

    # A seven-day account never reaches the forecaster's slow path — it is
    # turned away for want of history — so this does not need the long wait.
    expect(page.get_by_text("Insufficient transaction history for forecasting.")).to_be_visible(
        timeout=30000
    )
    # And no chart is displayed — the figures go with it.
    expect(page.locator(".nicegui-echart")).to_have_count(0)
    expect(page.locator("[data-kpi]")).to_have_count(0)


# ---------------------------------------------------------------------------
# Scenario: the figures include the scenario shifts the chart draws
# ---------------------------------------------------------------------------


def test_a_scenario_moves_the_predicted_figure(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-011, KAL-FCT-013

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
    before_confidence = _figure(page, "confidence")
    before_text = _kpi(page, "predicted").inner_text()

    # KAL-FCT-013 is a claim about what does *not* happen, so it is watched
    # for rather than checked after the fact: a forecast run always renders
    # the skeleton, and this records the skeleton ever entering the DOM.
    page.evaluate(
        """() => {
            window.__sawSkeleton = !!document.querySelector('.q-skeleton');
            new MutationObserver(() => {
                if (document.querySelector('.q-skeleton')) window.__sawSkeleton = true;
            }).observe(document.body, {childList: true, subtree: true});
        }"""
    )

    # A windfall a week from now: `seed_many_transactions` posts one today,
    # so the forecast runs from tomorrow and today + 7 is a point on it.
    # (`apply_scenarios` keys deltas by exact date — a date with no point
    # shifts nothing, which is why the dialog reads its own default off the
    # forecast rather than off the calendar.)
    when = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    page.get_by_text("Add scenario", exact=True).click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Label").fill("Bonus E2E")
    dialog.locator('input[type="date"]').fill(when)
    dialog.get_by_label("Amount (zł; negative for expenses)").fill("5000")
    dialog.get_by_role("button", name="Save").click()

    expect(_kpi(page, "predicted")).not_to_have_text(before_text, timeout=_REDRAW_TIMEOUT)
    assert _figure(page, "predicted") == pytest.approx(before_predicted + 5000, abs=0.01)
    assert _figure(page, "change") == pytest.approx(before_change + 5000, abs=0.01)
    # The interval moved with the line, so the ± did not move at all.
    assert _figure(page, "confidence") == pytest.approx(before_confidence, abs=0.01)

    # KAL-FCT-013: the skeleton never appeared, so no forecast was run —
    # `apply_scenarios` shifted the result already in hand.
    assert page.evaluate("() => window.__sawSkeleton") is False

    # Take it away again — both so the figure comes back, and so the scenario
    # does not follow the session into the next test.
    page.locator('[aria-label="Remove scenario Bonus E2E"]').click()
    expect(_kpi(page, "predicted")).to_have_text(before_text, timeout=_REDRAW_TIMEOUT)
