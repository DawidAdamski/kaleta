"""Unit tests for ForecastService — uses in-memory SQLite with Prophet mocked.

Prophet is mocked via unittest.mock.patch so tests run in milliseconds without
requiring the Prophet / Stan stack to be available.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    PlannedTransactionService,
    TransactionService,
)
from kaleta.services.forecast_service import ForecastService

# ── Helpers ────────────────────────────────────────────────────────────────────


async def _make_account(session: AsyncSession, name: str = "Main") -> int:
    acc = await AccountService(session).create(AccountCreate(name=name, type=AccountType.CHECKING))
    return acc.id


async def _make_category(session: AsyncSession, name: str = "Food") -> int:
    cat = await CategoryService(session).create(
        CategoryCreate(name=name, type=CategoryType.EXPENSE)
    )
    return cat.id


async def _seed_transactions(
    session: AsyncSession,
    account_id: int,
    n_days: int,
    amount: Decimal = Decimal("100.00"),
) -> None:
    """Insert one expense transaction per day for `n_days` days ending today.

    Expense type is used because it requires a category (like income), and
    ForecastService reads both income and expense rows for daily net cashflow.
    A seed category is created once per call.
    """
    cat_id = await _make_category(session)
    svc = TransactionService(session)
    today = datetime.date.today()
    for i in range(n_days):
        d = today - datetime.timedelta(days=n_days - 1 - i)
        await svc.create(
            TransactionCreate(
                account_id=account_id,
                category_id=cat_id,
                amount=amount,
                type=TransactionType.EXPENSE,
                date=d,
                description="seed",
            )
        )


def _make_prophet_result(
    start: datetime.date, n_history: int, n_forecast: int
) -> list[tuple[datetime.date, float, float, float]]:
    """Return a list of (date, yhat, yhat_lower, yhat_upper) tuples."""
    rows = []
    for i in range(n_history + n_forecast):
        d = start + datetime.timedelta(days=i)
        rows.append((d, float(1000 + i * 10), float(900 + i * 10), float(1100 + i * 10)))
    return rows


# ── Insufficient data ──────────────────────────────────────────────────────────


class TestForecastInsufficientData:
    async def test_returns_insufficient_data_when_no_transactions(self, session: AsyncSession):
        acc_id = await _make_account(session)
        svc = ForecastService(session)
        result = await svc.forecast_account(acc_id)
        assert result.insufficient_data is True
        assert result.points == []

    async def test_returns_insufficient_data_when_fewer_than_14_days(self, session: AsyncSession):
        """Service requires at least 14 distinct days to run Prophet."""
        acc_id = await _make_account(session)
        # Seed only 10 days of data
        await _seed_transactions(session, acc_id, n_days=10)
        svc = ForecastService(session)
        result = await svc.forecast_account(acc_id)
        assert result.insufficient_data is True
        assert result.points == []

    async def test_returns_insufficient_data_when_prophet_raises(self, session: AsyncSession):
        """If _run_prophet returns None (e.g. Prophet unavailable), service marks insufficient."""
        acc_id = await _make_account(session)
        # Seed enough data so we pass the 14-day check
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        # Patch _run_prophet to return None (simulates Prophet crash)
        with patch("kaleta.services.forecast_service._run_prophet", return_value=None):
            result = await svc.forecast_account(acc_id)

        assert result.insufficient_data is True
        assert result.points == []


# ── Successful forecast ────────────────────────────────────────────────────────


class TestForecastSuccess:
    async def test_returns_forecast_points_when_data_sufficient(self, session: AsyncSession):
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_prophet_result(history_start, n_history=20, n_forecast=60)

        with patch("kaleta.services.forecast_service._run_prophet", return_value=mock_result):
            result = await svc.forecast_account(acc_id, horizon_days=60)

        assert result.insufficient_data is False
        assert len(result.points) > 0

    async def test_result_contains_historical_and_forecast_points(self, session: AsyncSession):
        acc_id = await _make_account(session)
        n_days = 20
        await _seed_transactions(session, acc_id, n_days=n_days)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=n_days - 1)
        mock_result = _make_prophet_result(history_start, n_history=n_days, n_forecast=30)

        with patch("kaleta.services.forecast_service._run_prophet", return_value=mock_result):
            result = await svc.forecast_account(acc_id, horizon_days=30)

        assert len(result.historical) > 0
        assert len(result.forecast) > 0

    async def test_forecast_points_are_date_value_pairs(self, session: AsyncSession):
        """Each ForecastPoint has .date and .value attributes."""
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_prophet_result(history_start, n_history=20, n_forecast=10)

        with patch("kaleta.services.forecast_service._run_prophet", return_value=mock_result):
            result = await svc.forecast_account(acc_id, horizon_days=10)

        for point in result.points:
            assert isinstance(point.date, datetime.date)
            assert isinstance(point.value, float)

    async def test_account_name_in_result(self, session: AsyncSession):
        acc_id = await _make_account(session, name="Savings")
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_prophet_result(history_start, n_history=20, n_forecast=10)

        with patch("kaleta.services.forecast_service._run_prophet", return_value=mock_result):
            result = await svc.forecast_account(acc_id, horizon_days=10)

        assert result.account_name == "Savings"

    async def test_all_accounts_forecast_when_account_id_none(self, session: AsyncSession):
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_prophet_result(history_start, n_history=20, n_forecast=10)

        with patch("kaleta.services.forecast_service._run_prophet", return_value=mock_result):
            result = await svc.forecast_account(None, horizon_days=10)

        assert result.account_name == "All Accounts"
        assert result.insufficient_data is False


# ── Planned transactions overlay ───────────────────────────────────────────────


class TestForecastWithPlannedTransactions:
    async def test_planned_transactions_included_in_result(self, session: AsyncSession):
        """When planned transactions exist, result.planned_occurrences is non-empty."""
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)

        # Create a recurring planned expense starting tomorrow
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        pt_svc = PlannedTransactionService(session)
        await pt_svc.create(
            PlannedTransactionCreate(
                name="Monthly Rent",
                amount=Decimal("1000.00"),
                type=TransactionType.EXPENSE,
                account_id=acc_id,
                frequency=RecurrenceFrequency.MONTHLY,
                start_date=tomorrow,
            )
        )

        svc = ForecastService(session)
        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_prophet_result(history_start, n_history=20, n_forecast=60)

        with patch("kaleta.services.forecast_service._run_prophet", return_value=mock_result):
            result = await svc.forecast_account(acc_id, horizon_days=60)

        assert result.insufficient_data is False
        # There should be at least one planned occurrence in the 60-day window
        assert len(result.planned_occurrences) >= 1

    async def test_planned_transactions_adjust_forecast_values(self, session: AsyncSession):
        """A planned expense should reduce at least one forecast point's value."""
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)

        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        pt_svc = PlannedTransactionService(session)
        await pt_svc.create(
            PlannedTransactionCreate(
                name="Big Bill",
                amount=Decimal("500.00"),
                type=TransactionType.EXPENSE,
                account_id=acc_id,
                frequency=RecurrenceFrequency.ONCE,
                start_date=tomorrow,
            )
        )

        svc = ForecastService(session)
        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)

        # Provide stable mock data so we can reason about adjustments
        mock_result = _make_prophet_result(history_start, n_history=20, n_forecast=30)
        # Collect the raw yhat values for forecast points before overlay
        raw_forecast_values = {row[0]: row[1] for row in mock_result if row[0] > today}

        with patch("kaleta.services.forecast_service._run_prophet", return_value=mock_result):
            result = await svc.forecast_account(acc_id, horizon_days=30)

        # At least one forecast point on or after tomorrow should differ from raw
        adjusted_any = False
        for point in result.forecast:
            raw = raw_forecast_values.get(point.date)
            if raw is not None and abs(point.value - raw) > 0.01:
                adjusted_any = True
                break

        assert adjusted_any, "Expected at least one forecast point to be adjusted by planned tx"
