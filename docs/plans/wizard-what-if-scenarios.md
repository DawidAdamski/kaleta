---
plan_id: wizard-what-if-scenarios
title: Wizard — "what if" scenario simulator on top of the forecast engine
area: wizard
effort: large
status: draft
roadmap_ref: ../roadmap.md#forecast
---

# Wizard — "what if" scenarios

## Intent

The wizard tile "Scenariusze «co jeśli»" (`step_scenarios`, budget
section) is Coming soon. Its description is the spec: *"Simulates the
impact of income drops, big purchases, or new recurring expenses on
your monthly balance and emergency fund runway."* This is the panel
that answers "can I afford X?" without spreadsheet gymnastics.

## Prior art (build on, don't duplicate)

- **Forecast engine** — `forecast_service` with naive + optional
  Prophet forecasters and model presets
  (KAL-FCT scenarios, `forecast-model-presets` archived plan). The
  simulator is *deltas applied to a baseline projection*, not a new
  forecasting engine.
- **Emergency runway** — `reserve_fund` model has `months_of_coverage`
  and the survival-months footer in `safety_funds.py`; runway impact
  reuses that maths.
- **Cross-panel projection layer** — ADR-030 (read-only projections
  across panels) is the architectural slot this fits into.

## Scope

- **Scenario model (in-memory v1, no DB)**: a scenario = baseline
  forecast + a list of typed deltas:
  - income change: ±% or ±amount from month M (e.g. "income −30%
    from October"),
  - one-off purchase: amount + date (e.g. "buy a car for 40k in
    March"),
  - new recurring expense/income: amount + cadence + start date.
- **Simulation service** (pure): apply deltas to the baseline monthly
  balance projection; outputs per-month balance series, first month
  below zero (if any), and emergency-fund runway (months of essential
  spending covered) before vs after.
- **Panel page** at `/wizard/scenarios` (route in `_STEP_ROUTES`):
  - baseline chart (reuses forecast chart component),
  - delta builder (add/remove the three delta types),
  - before/after overlay + verdict strip ("balance stays positive;
    runway drops 5.2 → 3.1 months"),
  - works with the naive forecaster — Prophet must NOT be required
    (respect the optional-extra principle).
- **Persistence (stretch, keep only if cheap)**: save named scenarios
  per user; otherwise explicitly session-only in v1 — decide in Open
  questions before starting.
- **Product doc**: add a "What-if scenarios" section to
  `docs/product/financial-wizard.md` (spec-first).
- **BDD**: new Feature (`KAL-WIF`) with `@planned` scenarios: income
  drop shifts projected balance; one-off purchase shows runway before/
  after; new recurring expense moves the first-negative-month marker;
  panel functional without Prophet installed. Retag as tests land.

Out of scope: Monte Carlo / probabilistic bands, AI-suggested
scenarios (paid tier), scenario → budget writeback ("apply this
scenario to my plan" is a future plan), gift planning (KAL-GFT).

## Acceptance criteria

- `uv run pytest tests/unit/services -q`
- `grep -q "KAL-WIF-001" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` Without Prophet installed: build "income −30% + car 40k
  in March" on seed data; overlay renders, runway verdict updates,
  removing deltas restores the baseline exactly.

## Touchpoints

- `src/kaleta/services/` new `scenario_service.py` (+ types in
  `schemas/`)
- `src/kaleta/services/forecast_service.py` (baseline access — read
  only), `reserve_fund_service` (runway maths — read only)
- `src/kaleta/views/wizard.py` (`_STEP_ROUTES`), new view module,
  `views/chart_utils.py`
- `docs/product/financial-wizard.md`, `docs/bdd.md` (KAL-WIF)
- `tests/unit/services/`, `tests/e2e/`

## Open questions

1. Persist scenarios in v1? Default: **no** — session-only; a
   `saved_scenarios` table is a follow-up plan once the UX proves out.
2. Runway definition: essential-spending average from history (as the
   emergency-fund wizard computes it) or total average spending?
   Default: **same formula the Safety Funds panel already uses** —
   one definition across the app.
3. Horizon: default 12 months, max 24? Default: **yes** (matches
   forecast presets).

## Implementation notes

_Filled in as work progresses._
