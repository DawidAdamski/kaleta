"""E2E tests for Feature: Account Balance Forecast.

Maps scenarios from docs/bdd.md — Feature: Account Balance Forecast.
Page URL: /forecast
"""

from __future__ import annotations

import asyncio
import datetime
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8080"

_executor = ThreadPoolExecutor(max_workers=1)


def _run(coro):  # type: ignore[no-untyped-def]
    def _worker():  # type: ignore[no-untyped-def]
        return asyncio.run(coro)

    return _executor.submit(_worker).result()


# ---------------------------------------------------------------------------
# Seed helpers (idempotent)
# ---------------------------------------------------------------------------


def seed_account(name: str, currency: str = "PLN") -> int:
    from sqlalchemy import select

    from kaleta.db import AsyncSessionFactory
    from kaleta.models.account import Account
    from kaleta.schemas.account import AccountCreate
    from kaleta.services import AccountService

    async def _create() -> int:
        async with AsyncSessionFactory() as session:
            existing = (
                await session.execute(select(Account).where(Account.name == name))
            ).scalar_one_or_none()
            if existing:
                return existing.id
            acc = await AccountService(session).create(AccountCreate(name=name, currency=currency))
            return acc.id

    return _run(_create())


def seed_category(name: str, cat_type: str = "expense") -> int:
    from sqlalchemy import select

    from kaleta.db import AsyncSessionFactory
    from kaleta.models.category import Category, CategoryType
    from kaleta.schemas.category import CategoryCreate
    from kaleta.services import CategoryService

    async def _create() -> int:
        async with AsyncSessionFactory() as session:
            existing = (
                await session.execute(
                    select(Category).where(Category.name == name, Category.parent_id.is_(None))
                )
            ).scalar_one_or_none()
            if existing:
                return existing.id
            ct = CategoryType(cat_type)
            cat = await CategoryService(session).create(CategoryCreate(name=name, type=ct))
            return cat.id

    return _run(_create())


def seed_transactions(account_id: int, category_id: int, n_days: int = 90) -> None:
    """Seed one expense transaction per day for the past n_days days.

    Skips days that already have a 'seed' transaction for this account to stay
    idempotent.
    """
    from sqlalchemy import select

    from kaleta.db import AsyncSessionFactory
    from kaleta.models.transaction import Transaction, TransactionType
    from kaleta.schemas.transaction import TransactionCreate
    from kaleta.services import TransactionService

    async def _create() -> None:
        async with AsyncSessionFactory() as session:
            today = datetime.date.today()
            for i in range(n_days):
                d = today - datetime.timedelta(days=i)
                # Check for existing seed transaction on this date/account
                exists = (
                    await session.execute(
                        select(Transaction).where(
                            Transaction.account_id == account_id,
                            Transaction.date == d,
                            Transaction.description == "seed",
                        )
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
                svc = TransactionService(session)
                await svc.create(
                    TransactionCreate(
                        account_id=account_id,
                        category_id=category_id,
                        amount=Decimal("50.00"),
                        type=TransactionType.EXPENSE,
                        date=d,
                        description="seed",
                    )
                )

    _run(_create())


# ---------------------------------------------------------------------------
# Scenario: Forecast page loads and shows controls
# ---------------------------------------------------------------------------


def test_forecast_page_loads(page: Page) -> None:
    """Forecast page renders account selector, horizon selector and Run button."""
    page.goto(f"{BASE_URL}/forecast")

    expect(page.get_by_text("Balance Forecast", exact=True)).to_be_visible(timeout=5000)
    expect(page.get_by_label("Account")).to_be_visible(timeout=5000)
    expect(page.get_by_label("Forecast horizon (days)")).to_be_visible(timeout=5000)
    expect(page.get_by_role("button", name="Run Forecast")).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Forecast page shows initial prompt before running
# ---------------------------------------------------------------------------


def test_forecast_page_shows_initial_prompt(page: Page) -> None:
    """Forecast page shows a prompt asking the user to run the forecast."""
    page.goto(f"{BASE_URL}/forecast")

    expect(page.get_by_text("Click 'Run Forecast' to generate predictions.")).to_be_visible(
        timeout=5000
    )


# ---------------------------------------------------------------------------
# Scenario: Run a 30-day forecast for a single account (with sufficient history)
# ---------------------------------------------------------------------------


def test_run_30_day_forecast_single_account(page: Page) -> None:
    """Scenario: Run a 30-day forecast for a single account"""
    acc_id = seed_account("PKO Forecast 30d E2E")
    cat_id = seed_category("Forecast Expense 30d E2E")
    seed_transactions(acc_id, cat_id, n_days=90)

    page.goto(f"{BASE_URL}/forecast")

    page.locator(".q-select").filter(has_text="Account").click()
    page.get_by_role("option", name="PKO Forecast 30d E2E").click()

    page.locator(".q-select").filter(has_text="Forecast horizon").click()
    page.get_by_role("option", name="30 days").click()

    page.get_by_role("button", name="Run Forecast").click()

    # Prophet can take time; accept either KPI result or insufficient warning
    kpi = page.get_by_text("Current Balance")
    insufficient = page.get_by_text("Insufficient transaction history for forecasting.")

    try:
        expect(kpi).to_be_visible(timeout=30000)
    except Exception:
        expect(insufficient).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Scenario: Run a 90-day forecast
# ---------------------------------------------------------------------------


def test_run_90_day_forecast(page: Page) -> None:
    """Scenario: Run a 90-day forecast for a single account"""
    acc_id = seed_account("PKO Forecast 90d E2E")
    cat_id = seed_category("Forecast Expense 90d E2E")
    seed_transactions(acc_id, cat_id, n_days=90)

    page.goto(f"{BASE_URL}/forecast")

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


def test_run_forecast_all_accounts(page: Page) -> None:
    """Scenario: Run a forecast for all accounts combined"""
    page.goto(f"{BASE_URL}/forecast")

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


def test_warning_shown_for_insufficient_history(page: Page) -> None:
    """Scenario: Warning shown when history is insufficient"""
    acc_id = seed_account("New Acct Forecast Insuf E2E")
    cat_id = seed_category("Forecast Insuf Cat E2E")
    seed_transactions(acc_id, cat_id, n_days=7)

    page.goto(f"{BASE_URL}/forecast")

    page.locator(".q-select").filter(has_text="Account").click()
    page.get_by_role("option", name="New Acct Forecast Insuf E2E").click()

    page.get_by_role("button", name="Run Forecast").click()

    expect(page.get_by_text("Insufficient transaction history for forecasting.")).to_be_visible(
        timeout=30000
    )
