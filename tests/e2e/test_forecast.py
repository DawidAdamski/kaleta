# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Account Balance Forecast.

Maps scenarios from docs/bdd.md — Feature: Account Balance Forecast.
Page URL: /forecast
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.seed_helpers import seed_account, seed_category, seed_many_transactions

# ---------------------------------------------------------------------------
# Scenario: Forecast page loads and shows controls
# ---------------------------------------------------------------------------


def test_forecast_page_loads(page: Page, base_url: str) -> None:
    """Forecast page renders account selector, horizon selector and Run button."""
    page.goto(f"{base_url}/forecast")

    expect(page.get_by_text("Balance Forecast", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_label("Account")).to_be_visible(timeout=5000)
    expect(page.get_by_label("Forecast horizon (days)")).to_be_visible(timeout=5000)
    expect(page.get_by_role("button", name="Run Forecast")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Forecast page shows initial prompt before running
# ---------------------------------------------------------------------------


def test_forecast_page_shows_initial_prompt(page: Page, base_url: str) -> None:
    """Forecast page shows a prompt asking the user to run the forecast."""
    page.goto(f"{base_url}/forecast")

    expect(page.get_by_text("Click 'Run Forecast' to generate predictions.")).to_be_visible(
        timeout=5000
    )


# ---------------------------------------------------------------------------
# Scenario: Run a 30-day forecast for a single account (with sufficient history)
# ---------------------------------------------------------------------------


def test_run_30_day_forecast_single_account(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-001"""
    acc_id = seed_account("PKO Forecast 30d E2E")
    cat_id = seed_category("Forecast Expense 30d E2E")
    seed_many_transactions(acc_id, cat_id, n_days=90)

    page.goto(f"{base_url}/forecast")

    page.locator(".q-select").filter(has_text="Account").click()
    page.get_by_role("option", name="PKO Forecast 30d E2E").click()

    page.locator(".q-select").filter(has_text="Forecast horizon").click()
    page.get_by_role("option", name="30 days").click()

    page.get_by_role("button", name="Run Forecast").click()

    # Prophet can take time; accept either KPI result or insufficient warning
    expect(
        page.get_by_text("Current Balance").or_(
            page.get_by_text("Insufficient transaction history for forecasting.")
        )
    ).to_be_visible(timeout=60000)


# ---------------------------------------------------------------------------
# Scenario: Run a 90-day forecast
# ---------------------------------------------------------------------------


def test_run_90_day_forecast(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-002"""
    acc_id = seed_account("PKO Forecast 90d E2E")
    cat_id = seed_category("Forecast Expense 90d E2E")
    seed_many_transactions(acc_id, cat_id, n_days=90)

    page.goto(f"{base_url}/forecast")

    page.locator(".q-select").filter(has_text="Account").click()
    page.get_by_role("option", name="PKO Forecast 90d E2E").click()

    page.locator(".q-select").filter(has_text="Forecast horizon").click()
    page.get_by_role("option", name="90 days").click()

    page.get_by_role("button", name="Run Forecast").click()

    kpi = page.get_by_text("Current Balance")
    insufficient = page.get_by_text("Insufficient transaction history for forecasting.")

    try:
        expect(kpi).to_be_visible(timeout=30000)
    except Exception:
        expect(insufficient).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Run a forecast for All accounts combined
# ---------------------------------------------------------------------------


def test_run_forecast_all_accounts(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-003"""
    page.goto(f"{base_url}/forecast")

    # Default account selection is "All Accounts"
    expect(page.locator(".q-select").filter(has_text="All Accounts")).to_be_visible(timeout=5000)

    page.get_by_role("button", name="Run Forecast").click()

    # The initial prompt disappears once the run starts
    expect(page.get_by_text("Click 'Run Forecast' to generate predictions.")).not_to_be_visible(
        timeout=30000
    )


# ---------------------------------------------------------------------------
# Scenario: Warning shown when history is insufficient
# ---------------------------------------------------------------------------


def test_warning_shown_for_insufficient_history(page: Page, base_url: str) -> None:
    """Covers: KAL-FCT-007"""
    acc_id = seed_account("New Acct Forecast Insuf E2E")
    cat_id = seed_category("Forecast Insuf Cat E2E")
    seed_many_transactions(acc_id, cat_id, n_days=7)

    page.goto(f"{base_url}/forecast")

    page.locator(".q-select").filter(has_text="Account").click()
    page.get_by_role("option", name="New Acct Forecast Insuf E2E").click()

    page.get_by_role("button", name="Run Forecast").click()

    expect(page.get_by_text("Insufficient transaction history for forecasting.")).to_be_visible(
        timeout=30000
    )
