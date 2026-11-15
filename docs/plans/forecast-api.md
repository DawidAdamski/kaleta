---
plan_id: forecast-api
title: Balance forecast REST API (read-only)
area: api, forecast
effort: small
status: draft
roadmap_ref: ../roadmap.md
---

# Balance forecast REST API (read-only)

## Intent
The Forecast page answers "where will this account's balance be in N days?",
but an API client (a script, Claude) cannot ask. `ForecastService.forecast_account`
and the pure helpers beside it (`apply_preset`, `forecast_kpis`) are not
exposed under `/api/v1`. Expose one read-only endpoint over the existing service
and change no forecasting behaviour. The service does need two small fixes before
the API can call it safely: its process-wide result cache is shared across
families, and it returns a made-up name for an unknown account where it should
fail.

## What the code does today (grounding)
- **Prophet is optional**, through the `forecast` extra in `pyproject.toml`. It is
  installed neither by `uv sync --group dev` nor in CI. Without it nothing fails:
  `kaleta.services.forecasters.get_forecaster()` returns `NaiveForecaster`, and
  `active_forecaster_model()` reports `"naive"`. **`ForecastUnavailableError` is
  never raised anywhere in `src/`.** It is defined in `kaleta.exceptions` and
  `kaleta_error_http_status` maps it to 503, but this plan has no reason to start
  raising it (see Open questions).
- **The event loop is not blocked.** `forecast_account` already runs
  `forecaster.run(running, horizon_days)` through
  `asyncio.get_event_loop().run_in_executor(None, partial(...))`. The views
  (`views/forecast.py`, `views/wizard_scenarios.py`, the dashboard widgets) just
  `await` the service. The route does the same and needs no executor of its own.
- **Minimum history**: the service needs at least 14 distinct days with
  non-internal, non-loan-linked INCOME/EXPENSE rows in the last `history_days`
  (default 365). Below that, or when the forecaster returns `None` (Prophet
  raising inside `ProphetForecaster.run` is swallowed into `None`), it returns
  `ForecastResult(points=[], insufficient_data=True)` and does not raise.
- **The horizon** is uncapped in the service. The UI offers 30/60/90 days
  (`_HORIZONS`), and the scenario wizard goes up to
  `MAX_HORIZON_MONTHS * _DAYS_PER_MONTH` = 24 × 30 = 720 days.
- **Point values are floats** (`ForecastPoint.value/lower/upper`), rounded to 2 dp.
  History points (`is_forecast=False`) come first, then exactly `horizon_days`
  forecast points that start the day after the last *transaction*, not today.
  Both backends share this shape.
- **Unknown account**: `forecast_account(999)` names the result `"Account 999"` and
  goes on querying. It raises nothing.
- **Cache leak**: `_forecast_cache` is a module-global dict keyed by
  `_ForecastCacheKey(account_id, horizon_days, history_days, model)`, with no
  family. In a hosted, multi-family process, family B's "All accounts" (or its
  account id 3) can get family A's cached series. The API makes this reachable by
  any family's token.

## Scope
- `GET /api/v1/forecast/balance` → `ForecastResponse`, in a new router
  `src/kaleta/api/v1/forecast.py` (`prefix="/forecast"`, `tags=["Forecast"]`),
  registered in `src/kaleta/api/v1/__init__.py`. Session through
  `kaleta.api.deps.get_session`. Query parameters:
  - `account_id: int | None = None`. Omitted means all accounts, as in the service.
  - `horizon_days: int = Query(60, ge=1, le=720)`. The default matches the
    service. The cap is the scenario wizard's maximum, so a later scenarios
    endpoint shares it. Outside the range → 422 (FastAPI validation, envelope).
  - `preset: ForecastPreset = ForecastPreset.BASELINE`, applied with the existing
    pure `apply_preset(result, preset)`.
- `ForecastResponse` in a new `src/kaleta/schemas/forecast.py`:
  - `account_id: int | None`, `account_name: str`, `horizon_days: int`,
    `preset: str` (the preset's value), `forecaster_model: str` (`"prophet"` or
    `"naive"`, taken from `ForecastResult.forecaster_model`),
    `insufficient_data: bool`
  - `points: list[ForecastPointResponse]`, each with `date: datetime.date`,
    `value: Decimal`, `lower: Decimal`, `upper: Decimal`, `is_forecast: bool`
  - `kpis: ForecastKpisResponse | None`, read from `forecast_kpis(result)` on the preset-applied result.
    The fields are `balance_today`, `balance_date`, `predicted`, `change`,
    `confidence` and `horizon_date`, with the money ones as `Decimal | None`. It
    is `None` when `insufficient_data`.
- **Money as `Decimal`, not float.** Every other money field in the API is
  `Decimal` and serializes as a JSON string (`CashflowMonthResponse`,
  `NetWorthSnapshotResponse`), so a client parses all money one way.
  `ScenarioVerdict` already turns forecast floats into Decimals the same way
  (`scenario_service._ending_balance`): `Decimal(str(v)).quantize(Decimal("0.01"),
  ROUND_HALF_UP)`. The values are estimates, but the service has already rounded
  them to 2 dp, so the conversion loses nothing a float would keep. The route
  does the conversion when it maps the dataclass into the schema, as `reports.py`
  maps its rows. The schema imports nothing from `kaleta.services`.
- Service change 1, **404 for an unknown account**: in
  `ForecastService.forecast_account`, when `account_id is not None` and
  `session.get(Account, account_id)` is `None`, raise
  `NotFoundError(f"Account {account_id} not found")` instead of the
  `"Account {id}"` fallback. This is safe for the UI: `views/forecast.py`
  `_saved_account` only offers ids that exist, and both forecast views catch
  `KaletaError`.
- Service change 2, **a cache key per family**: add `schema: str | None` to
  `_ForecastCacheKey`, filled from `kaleta.db.tenant_context.current_tenant()`
  (`ctx.schema`, `None` when no tenant is set, i.e. the single-family layout).
  This is the same lookup `transaction_service` and `import_pipeline` already do.
- Insufficient history is **200** with `insufficient_data: true`, `points: []` and
  `kpis: null`. It is not an error: the request is valid and the account simply
  has too little history to forecast from.

### Scenario (paste into `docs/bdd.md`, the API feature block, right after KAL-API-009)

```gherkin
  KAL-API-019 @automated
  Scenario: Read an account's balance forecast through the API
    Given a valid API bearer token
    And an account "PKO Main" with income and expense rows on 20 distinct days in the last 60 days
    When I GET /api/v1/forecast/balance?account_id={PKO Main}&horizon_days=30
    Then the response is 200 with account_name "PKO Main" and insufficient_data false
    And it holds exactly 30 points with is_forecast true, after the history points
    And the point dates strictly increase, and every forecast point has lower <= value <= upper
    And value, lower and upper are decimal strings with two places
    And forecaster_model is "prophet" or "naive", and kpis gives the predicted balance on the last point's date
    When I GET it with preset=conservative
    Then no forecast value is above the baseline's value on the same date
    When the account has rows on only 5 distinct days
    Then the response is 200 with insufficient_data true, no points and kpis null
    And an unknown account_id is 404
    And horizon_days 0 or 721 is 422
    And a request without credentials is 401
```

## Out of scope
- **What-if scenarios (`ScenarioService.simulate`).** `simulate` is deterministic
  once it has a baseline. But an endpoint needs a fresh forecast first, then a
  request schema for `list[ScenarioDelta]`, a months/days horizon decision
  (`horizon_days(months)`), and a response for `ScenarioSimulation`
  (`baseline`, `projected`, `ScenarioVerdict`, `shifts`, `pins`). Its runway also
  reads `ReserveFundService` across the household. That needs design choices, so
  it goes in a follow-up plan (`forecast-scenarios-api`) that reuses this plan's
  schemas. The single-shift overlay `apply_scenarios` / `ScenarioShift` is left
  out too.
- A `GET /forecast/accounts` mirror of `available_accounts()`: `GET /api/v1/accounts`
  already lists them.
- Exposing `history_days`. The service default of 365 stays fixed.
- `planned_occurrences` in the response. They need a `TransactionType` in a schema,
  and the planned-transactions API is a separate concern.
- Changing how either forecaster computes, choosing the backend per request, or
  installing Prophet in CI.
- Cache staleness: `_forecast_cache` is never invalidated, so a transaction added
  after the first run is not reflected until restart. The UI has the same
  behaviour today. The implementer adds a checkbox for it to `docs/plans/chores.md`.
- Replacing the deprecated `asyncio.get_event_loop()` in the service with
  `get_running_loop()`. Add a chore line for it too.
- Capping the number of concurrent forecaster runs (default executor pool).

## Acceptance criteria
- `uv run pytest tests/integration/test_api_forecast.py -q`
- `uv run pytest tests/unit/services/test_forecast_service.py -q`
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`
- `grep -c "KAL-API-019" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- Tests live in the new `tests/integration/test_api_forecast.py`, with module and
  test docstrings carrying `Covers: KAL-API-019`. An autouse fixture calls
  `clear_forecast_cache()` before and after each test. It monkeypatches
  `kaleta.services.forecast_service.get_forecaster` to return `NaiveForecaster()`
  and `kaleta.services.forecast_service.active_forecaster_model` to return
  `"naive"`, so results do not depend on whether a developer has the `forecast`
  extra installed. No test fits Prophet, so none needs `@pytest.mark.slow`.
- No test asserts a forecast number. They assert status, length, ordering, band
  containment, decimal formatting and field presence, using the BDD literals
  (30 points, 20 / 5 distinct days, 404 / 422 / 401).
- Tests: `test_forecast_returns_horizon_points_after_history` (200, account_name,
  exactly 30 `is_forecast` points, all after the last history point, dates
  strictly increasing).
- Tests: `test_forecast_band_contains_value_and_money_is_decimal_strings`
  (`lower <= value <= upper` on forecast points, each money field matches
  `^-?\d+\.\d{2}$`).
- Tests: `test_kpis_point_at_last_forecast_day` (`kpis.horizon_date` equals the last
  point's date and `kpis.predicted` equals its value).
- Tests: `test_conservative_preset_is_not_above_baseline` (pairwise by date).
- Tests: `test_all_accounts_when_account_id_omitted` (200, account_name
  "All Accounts").
- Tests: `test_insufficient_history_is_200_with_flag` (5 distinct days → flag true,
  `points == []`, `kpis is None`).
- Tests: `test_unknown_account_is_404` (envelope code `not_found`).
- Tests: `test_horizon_out_of_range_is_422` (0 and 721).
- Tests: `test_forecast_requires_auth` (via `api_client_unauth`, 401).
- Tests: `test_forecast_cache_is_per_family`. Run `ForecastService.forecast_account`
  twice under `use_tenant(TenantContext(tenant_id=…, schema=…))` with two
  different schemas and a counting fake forecaster: the second family is a cache
  miss, so the forecaster runs twice. A repeat under the first family is a hit.
- Tests: `test_openapi_lists_forecast_operation_with_summary`
  (`app.openapi()` has `/api/v1/forecast/balance` GET with a summary).

## Touchpoints
- `src/kaleta/api/v1/forecast.py` (new), `src/kaleta/api/v1/__init__.py` (register)
- `src/kaleta/schemas/forecast.py` (new)
- `src/kaleta/services/forecast_service.py`: `forecast_account` raises
  `NotFoundError`, and `_ForecastCacheKey` gains `schema`
- `tests/integration/test_api_forecast.py` (new)
- `tests/unit/services/test_forecast_service.py`: read only, must stay green.
  Adjust only if a test constructs `_ForecastCacheKey` positionally.
- `docs/bdd.md` (KAL-API-019), `docs/plans/chores.md` (two chore lines)

## Open questions
- Should the API raise `ForecastUnavailableError` (503) when Prophet is missing?
  Default: **no**. Missing Prophet already degrades to the naive model by design,
  and the response's `forecaster_model` tells the client which one ran. 503 stays
  unused. Record this in Implementation notes.
- Should "the forecaster returned `None`" (Prophet crashed) be 503 instead of
  `insufficient_data`? Default: **no**. The service cannot tell it apart from short
  history without a behaviour change the UI would also see. Keep the
  `insufficient_data` flag.
- Endpoint shape: `/forecast/balance?account_id=` or `/accounts/{id}/forecast`?
  Default: `/forecast/balance` with an optional `account_id`, because "all
  accounts" is a first-class case with no id.
- Horizon cap of 720 or 365? Default: **720** (`MAX_HORIZON_MONTHS * 30`), so the
  scenarios follow-up can share it. A naive run is cheap, and a Prophet run at
  720 is still one fit in the executor.
- Seeding: through services or ORM rows? Default: the ORM rows the existing
  integration tests use (account + transactions on the test session). Dates are
  relative to `datetime.date.today()` and fall inside the 365-day window.
- Do the history points belong in the response, or only the forecast?
  Default: include them, with `is_forecast` as in the dataclass, because the
  page draws both and `kpis.balance_today` reads the last history point.

## Implementation notes
