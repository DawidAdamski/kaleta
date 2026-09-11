---
plan_id: restyle-forecast-on-load
title: Restyle — Forecast runs baseline on load, controls on the title row, one linear-axis chart (artboard 3a)
area: forecast
effort: medium
status: draft
roadmap_ref: ../roadmap.md#forecast
---

# Restyle — Forecast runs on load, one chart, four KPIs

## Intent

`views/forecast.py` opens empty behind a Run button. Artboard `3a` runs
the baseline on load and demotes Run to a re-run; the account / horizon
/ preset controls move onto the title row so the first thing you see is
a forecast. Four KPIs: balance today, predicted at horizon, change,
confidence. One ECharts instance: solid ink actuals, dashed accent
prediction, `#EFCDB2` confidence band, dotted muted baseline when a
non-baseline preset is active, a dashed `markLine` at today, and a
`markLine` + point per scenario. The Prophet-unavailable banner shrinks
to a footnote under the chart title.

Two things the prototype got wrong first and the plan must get right:
the x-axis must be **linear across history and forecast** (a category
axis over sparse dates compresses history), and the KPI figures must
include the scenario shifts if the chart's line does.

Depends on `restyle-theme-tokens` (chart palette).

## Scope

- **Run on load**: on page open, run the baseline forecast for the
  saved account / horizon / preset (`app.storage.user` keys
  `forecast_preset`, `forecast_scenarios` keep working; add
  `forecast_account`, `forecast_horizon`). Show a skeleton while it
  runs; Run becomes "Re-run" and is only needed after changing controls
  (or auto-run on change — see open question).
- **Title row**: page title left; account select, horizon select,
  preset toggle right, compact (no floating labels). Prophet footnote
  under the chart title with the docs link, replaces the amber banner.
- **KPIs**: today's balance, predicted at horizon, change (signed,
  `k-amount`), confidence at horizon (interval width as ±). Computed
  from the same series the chart draws, scenario shifts included.
- **Chart** (`_forecast_chart`): `xAxis.type = "time"`; series: actuals
  (ink, solid), prediction (accent, dashed), confidence band (two
  stacked series with `areaStyle` `#EFCDB2`, dark: accent at 0.18
  opacity), baseline (muted, dotted) only when preset ≠ baseline,
  `markLine` at today (dashed border colour), one `markLine` + point per
  scenario. Axis styling through `chart_utils.apply_dark`.
- Scenario chips: keep add / remove and persistence; restyle as
  `k-filter-chip`s.
- BDD: extend Account Balance Forecast — `KAL-FCT-010` "forecast page
  shows a baseline without pressing Run" (@automated, e2e) and
  `KAL-FCT-011` "KPIs include scenario shifts" (@automated, unit on the
  KPI helper).

Out of scope: forecaster models / presets (`forecast-model-presets`,
archived); scenario semantics; What-if scenarios plan
(`wizard-what-if-scenarios`, draft — that plan should build on this
chart, note it there).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_forecast_service.py -q`
- `uv run pytest tests/e2e/test_forecast.py -q`
- `grep -q '"time"' src/kaleta/views/forecast.py`
- `grep -q "KAL-FCT-010" docs/bdd.md`
- `grep -q "KAL-FCT-011" docs/bdd.md`
- `test "$(grep -c 'bg-amber-1' src/kaleta/views/forecast.py)" = 0`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Open /forecast on seed data: a chart is visible within a
  few seconds with no click; history is not compressed relative to the
  forecast segment; add a scenario: a marker appears and the predicted
  KPI moves by the scenario amount. Compare to artboard `3a` in light
  and dark, with and without Prophet installed.

## Touchpoints

- `src/kaleta/views/forecast.py` (page, `_forecast_chart`, `_kpi`)
- `src/kaleta/views/chart_utils.py`
- `src/kaleta/services/forecast_service.py` (KPI helper if it lives in
  the service; no model change)
- `src/kaleta/i18n/locales/en.json`, `pl.json` (`forecast.rerun`,
  `forecast.kpi_confidence`, footnote key)
- `docs/bdd.md`, `tests/e2e/test_forecast.py`, `tests/unit/`

## Open questions

1. Auto-run on every control change or explicit Re-run? Default:
   **auto-run on change with a 300 ms debounce**; Re-run stays for the
   Prophet case where a run is slow (>2 s) — then changes only mark the
   chart stale and Re-run applies them.
2. Confidence KPI format? Default: **`± X zł`** (half the interval width
   at horizon), tooltip explains.

## Implementation notes

_Filled in as work progresses._
