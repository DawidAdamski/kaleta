"""Unit tests for forecast backends and ForecastService."""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

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
from kaleta.services.forecast_service import (
    ForecastPoint,
    ForecastPreset,
    ForecastResult,
    ForecastService,
    ScenarioShift,
    _forecast_cache,
    apply_preset,
    apply_scenarios,
    clear_forecast_cache,
)
from kaleta.services.forecasters import (
    NaiveForecaster,
    active_forecaster_model,
    get_forecaster,
    is_prophet_available,
)

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


def _make_forecaster_result(
    start: datetime.date, n_history: int, n_forecast: int
) -> list[tuple[datetime.date, float, float, float]]:
    rows = []
    for i in range(n_history + n_forecast):
        d = start + datetime.timedelta(days=i)
        rows.append((d, float(1000 + i * 10), float(900 + i * 10), float(1100 + i * 10)))
    return rows


def _mock_forecaster(result: list | None, *, model_name: str = "prophet") -> MagicMock:
    forecaster = MagicMock()
    forecaster.model_name = model_name
    forecaster.run.return_value = result
    return forecaster


# ── Forecaster selection ───────────────────────────────────────────────────────


class TestForecasterSelection:
    def test_returns_naive_when_prophet_not_importable(self) -> None:
        with patch("kaleta.services.forecasters._prophet_importable", return_value=False):
            from kaleta.services.forecasters import _prophet_importable

            _prophet_importable.cache_clear()
            assert is_prophet_available() is False
            assert active_forecaster_model() == "naive"
            assert isinstance(get_forecaster(), NaiveForecaster)
            _prophet_importable.cache_clear()

    def test_returns_prophet_when_importable(self) -> None:
        with patch("kaleta.services.forecasters._prophet_importable", return_value=True):
            from kaleta.services.forecasters import _prophet_importable
            from kaleta.services.forecasters.prophet_forecaster import ProphetForecaster

            _prophet_importable.cache_clear()
            assert is_prophet_available() is True
            assert active_forecaster_model() == "prophet"
            assert isinstance(get_forecaster(), ProphetForecaster)
            _prophet_importable.cache_clear()


# ── NaiveForecaster ────────────────────────────────────────────────────────────


class TestNaiveForecaster:
    def test_returns_none_when_fewer_than_14_days(self) -> None:
        today = datetime.date.today()
        running = {today - datetime.timedelta(days=i): 1000.0 + i for i in range(10)}
        assert NaiveForecaster().run(running, horizon_days=30) is None

    def test_returns_historical_and_forecast_rows(self) -> None:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=29)
        running = {start + datetime.timedelta(days=i): 1000.0 + i * 5 for i in range(30)}
        rows = NaiveForecaster().run(running, horizon_days=14)
        assert rows is not None
        assert len(rows) == 30 + 14
        hist_dates = set(running.keys())
        forecast_rows = [r for r in rows if r[0] not in hist_dates]
        assert len(forecast_rows) == 14

    def test_forecast_band_contains_point_estimate(self) -> None:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=29)
        running = {start + datetime.timedelta(days=i): 1000.0 + i * 5 for i in range(30)}
        rows = NaiveForecaster().run(running, horizon_days=7)
        assert rows is not None
        for _, yhat, lower, upper in rows:
            assert lower <= yhat <= upper

    def test_model_name_is_naive(self) -> None:
        assert NaiveForecaster().model_name == "naive"


# ── Forecast cache ─────────────────────────────────────────────────────────────


class TestForecastCache:
    async def test_cache_key_includes_model(self, session: AsyncSession) -> None:
        clear_forecast_cache()
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_forecaster_result(history_start, n_history=20, n_forecast=10)
        forecaster = _mock_forecaster(mock_result)

        with (
            patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster),
            patch(
                "kaleta.services.forecast_service.active_forecaster_model",
                return_value="naive",
            ),
        ):
            await svc.forecast_account(acc_id, horizon_days=10)
            assert any(k.model == "naive" for k in _forecast_cache)
            forecaster.run.reset_mock()
            await svc.forecast_account(acc_id, horizon_days=10)
            forecaster.run.assert_not_called()

        clear_forecast_cache()

    async def test_different_model_bypasses_cache(self, session: AsyncSession) -> None:
        clear_forecast_cache()
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_forecaster_result(history_start, n_history=20, n_forecast=10)
        forecaster = _mock_forecaster(mock_result)

        with (
            patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster),
            patch(
                "kaleta.services.forecast_service.active_forecaster_model",
                side_effect=["naive", "prophet"],
            ),
        ):
            await svc.forecast_account(acc_id, horizon_days=10)
            await svc.forecast_account(acc_id, horizon_days=10)
            assert forecaster.run.call_count == 2

        clear_forecast_cache()


# ── Insufficient data ──────────────────────────────────────────────────────────


class TestForecastInsufficientData:
    async def test_returns_insufficient_data_when_no_transactions(self, session: AsyncSession):
        acc_id = await _make_account(session)
        svc = ForecastService(session)
        result = await svc.forecast_account(acc_id)
        assert result.insufficient_data is True
        assert result.points == []

    async def test_returns_insufficient_data_when_fewer_than_14_days(self, session: AsyncSession):
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=10)
        svc = ForecastService(session)
        result = await svc.forecast_account(acc_id)
        assert result.insufficient_data is True
        assert result.points == []

    async def test_returns_insufficient_data_when_forecaster_fails(self, session: AsyncSession):
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)
        forecaster = _mock_forecaster(None)

        with patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster):
            result = await svc.forecast_account(acc_id)

        assert result.insufficient_data is True
        assert result.points == []


# ── Successful forecast ────────────────────────────────────────────────────────


class TestForecastSuccess:
    async def test_returns_forecast_points_when_data_sufficient(self, session: AsyncSession):
        clear_forecast_cache()
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_forecaster_result(history_start, n_history=20, n_forecast=60)
        forecaster = _mock_forecaster(mock_result)

        with patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster):
            result = await svc.forecast_account(acc_id, horizon_days=60)

        assert result.insufficient_data is False
        assert len(result.points) > 0
        clear_forecast_cache()

    async def test_result_contains_historical_and_forecast_points(self, session: AsyncSession):
        clear_forecast_cache()
        acc_id = await _make_account(session)
        n_days = 20
        await _seed_transactions(session, acc_id, n_days=n_days)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=n_days - 1)
        mock_result = _make_forecaster_result(history_start, n_history=n_days, n_forecast=30)
        forecaster = _mock_forecaster(mock_result)

        with patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster):
            result = await svc.forecast_account(acc_id, horizon_days=30)

        assert len(result.historical) > 0
        assert len(result.forecast) > 0
        clear_forecast_cache()

    async def test_forecast_points_are_date_value_pairs(self, session: AsyncSession):
        clear_forecast_cache()
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_forecaster_result(history_start, n_history=20, n_forecast=10)
        forecaster = _mock_forecaster(mock_result)

        with patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster):
            result = await svc.forecast_account(acc_id, horizon_days=10)

        for point in result.points:
            assert isinstance(point.date, datetime.date)
            assert isinstance(point.value, float)
        clear_forecast_cache()

    async def test_account_name_in_result(self, session: AsyncSession):
        clear_forecast_cache()
        acc_id = await _make_account(session, name="Savings")
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_forecaster_result(history_start, n_history=20, n_forecast=10)
        forecaster = _mock_forecaster(mock_result)

        with patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster):
            result = await svc.forecast_account(acc_id, horizon_days=10)

        assert result.account_name == "Savings"
        clear_forecast_cache()

    async def test_all_accounts_forecast_when_account_id_none(self, session: AsyncSession):
        clear_forecast_cache()
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        today = datetime.date.today()
        history_start = today - datetime.timedelta(days=19)
        mock_result = _make_forecaster_result(history_start, n_history=20, n_forecast=10)
        forecaster = _mock_forecaster(mock_result)

        with patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster):
            result = await svc.forecast_account(None, horizon_days=10)

        assert result.account_name == "All Accounts"
        assert result.insufficient_data is False
        clear_forecast_cache()

    async def test_naive_forecaster_integration_without_mock(self, session: AsyncSession):
        """End-to-end through service with naive backend (Prophet mocked away)."""
        clear_forecast_cache()
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)
        svc = ForecastService(session)

        with patch("kaleta.services.forecasters._prophet_importable", return_value=False):
            from kaleta.services.forecasters import _prophet_importable

            _prophet_importable.cache_clear()
            result = await svc.forecast_account(acc_id, horizon_days=30)
            _prophet_importable.cache_clear()

        assert result.insufficient_data is False
        assert result.forecaster_model == "naive"
        assert len(result.forecast) == 30
        clear_forecast_cache()


# ── Planned transactions overlay ───────────────────────────────────────────────


class TestForecastWithPlannedTransactions:
    async def test_planned_transactions_included_in_result(self, session: AsyncSession):
        clear_forecast_cache()
        acc_id = await _make_account(session)
        await _seed_transactions(session, acc_id, n_days=20)

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
        mock_result = _make_forecaster_result(history_start, n_history=20, n_forecast=60)
        forecaster = _mock_forecaster(mock_result)

        with patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster):
            result = await svc.forecast_account(acc_id, horizon_days=60)

        assert result.insufficient_data is False
        assert len(result.planned_occurrences) >= 1
        clear_forecast_cache()

    async def test_planned_transactions_adjust_forecast_values(self, session: AsyncSession):
        clear_forecast_cache()
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
        mock_result = _make_forecaster_result(history_start, n_history=20, n_forecast=30)
        raw_forecast_values = {row[0]: row[1] for row in mock_result if row[0] > today}
        forecaster = _mock_forecaster(mock_result)

        with patch("kaleta.services.forecast_service.get_forecaster", return_value=forecaster):
            result = await svc.forecast_account(acc_id, horizon_days=30)

        adjusted_any = False
        for point in result.forecast:
            raw = raw_forecast_values.get(point.date)
            if raw is not None and abs(point.value - raw) > 0.01:
                adjusted_any = True
                break

        assert adjusted_any
        clear_forecast_cache()


# ── Pure-function helpers: apply_preset / apply_scenarios ──────────────────────


def _sample_result() -> ForecastResult:
    today = datetime.date(2025, 6, 1)
    return ForecastResult(
        account_name="Main",
        points=[
            ForecastPoint(
                date=today - datetime.timedelta(days=2),
                value=1000.0,
                lower=1000.0,
                upper=1000.0,
                is_forecast=False,
            ),
            ForecastPoint(
                date=today - datetime.timedelta(days=1),
                value=1000.0,
                lower=1000.0,
                upper=1000.0,
                is_forecast=False,
            ),
            ForecastPoint(
                date=today,
                value=1100.0,
                lower=900.0,
                upper=1300.0,
                is_forecast=True,
            ),
            ForecastPoint(
                date=today + datetime.timedelta(days=1),
                value=1200.0,
                lower=1000.0,
                upper=1400.0,
                is_forecast=True,
            ),
            ForecastPoint(
                date=today + datetime.timedelta(days=2),
                value=1300.0,
                lower=1100.0,
                upper=1500.0,
                is_forecast=True,
            ),
        ],
    )


class TestApplyPreset:
    def test_baseline_is_passthrough(self) -> None:
        orig = _sample_result()
        out = apply_preset(orig, ForecastPreset.BASELINE)
        assert out is orig
        assert [p.value for p in out.forecast] == [1100.0, 1200.0, 1300.0]

    def test_conservative_blends_toward_lower(self) -> None:
        out = apply_preset(_sample_result(), ForecastPreset.CONSERVATIVE)
        assert [p.value for p in out.forecast] == [1000.0, 1100.0, 1200.0]

    def test_optimistic_blends_toward_upper(self) -> None:
        out = apply_preset(_sample_result(), ForecastPreset.OPTIMISTIC)
        assert [p.value for p in out.forecast] == [1200.0, 1300.0, 1400.0]

    def test_leaves_historical_untouched(self) -> None:
        orig = _sample_result()
        out = apply_preset(orig, ForecastPreset.CONSERVATIVE)
        assert [p.value for p in out.historical] == [1000.0, 1000.0]

    def test_does_not_mutate_input(self) -> None:
        orig = _sample_result()
        before = [p.value for p in orig.forecast]
        apply_preset(orig, ForecastPreset.CONSERVATIVE)
        assert [p.value for p in orig.forecast] == before


class TestApplyScenarios:
    def test_empty_shift_list_is_passthrough(self) -> None:
        orig = _sample_result()
        assert apply_scenarios(orig, []) is orig

    def test_single_shift_affects_that_date_and_after(self) -> None:
        today = datetime.date(2025, 6, 1)
        out = apply_scenarios(
            _sample_result(),
            [
                ScenarioShift(
                    label="windfall", date=today + datetime.timedelta(days=1), amount=500.0
                )
            ],
        )
        vals = [p.value for p in out.forecast]
        assert vals == [1100.0, 1700.0, 1800.0]

    def test_shifts_stack_cumulatively(self) -> None:
        today = datetime.date(2025, 6, 1)
        out = apply_scenarios(
            _sample_result(),
            [
                ScenarioShift(label="raise", date=today, amount=100.0),
                ScenarioShift(
                    label="purchase",
                    date=today + datetime.timedelta(days=2),
                    amount=-50.0,
                ),
            ],
        )
        vals = [p.value for p in out.forecast]
        assert vals == [1200.0, 1300.0, 1350.0]

    def test_shift_moves_interval_too(self) -> None:
        today = datetime.date(2025, 6, 1)
        out = apply_scenarios(
            _sample_result(),
            [ScenarioShift(label="x", date=today, amount=200.0)],
        )
        first = out.forecast[0]
        assert first.value == 1300.0
        assert first.lower == 1100.0
        assert first.upper == 1500.0

    def test_past_dated_shift_is_ignored(self) -> None:
        today = datetime.date(2025, 6, 1)
        out = apply_scenarios(
            _sample_result(),
            [ScenarioShift(label="x", date=today - datetime.timedelta(days=5), amount=999.0)],
        )
        assert [p.value for p in out.forecast] == [1100.0, 1200.0, 1300.0]
        assert [p.value for p in out.historical] == [1000.0, 1000.0]

    def test_does_not_mutate_input(self) -> None:
        orig = _sample_result()
        before = [p.value for p in orig.forecast]
        apply_scenarios(
            orig,
            [ScenarioShift(label="x", date=orig.forecast[0].date, amount=50.0)],
        )
        assert [p.value for p in orig.forecast] == before
