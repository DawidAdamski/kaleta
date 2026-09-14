---
plan_id: restyle-forecast-on-load
title: Restyle — Forecast runs baseline on load, controls on the title row, one linear-axis chart (artboard 3a)
area: forecast
effort: medium
status: in-progress
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

### Open questions, resolved

1. **Auto-run on control change, or an explicit Re-run?** Plan default, taken
   as written: auto-run with a 300 ms debounce when the naive projection is
   in use, and, when Prophet is installed and a run costs seconds, a change
   only marks the chart stale — `stale_hint` under the title, the Re-run
   button raised out of `flat` — and Re-run applies it. `is_prophet_available()`
   is the proxy for "a run is slow", which is the plan's own wording.
2. **Confidence KPI format?** Plan default: `± X zł`, half the 80 % interval
   at the horizon, with the hint line under the figure saying so.

### The band was drawn above the line it was meant to surround

Not a restyle: a bug the restyle uncovered. The band is drawn by stacking its
height on an invisible floor series, and the floor was the **upper** bound —
so the shading ran from `upper` to `2·upper − lower`, sitting entirely above
the prediction. `KAL-FCT-001` has said "a shaded confidence interval
surrounds the prediction" all along. The floor is the lower bound now, and
`tests/unit/views/test_forecast_chart.py` asserts floor + height = upper.

### The x-axis is time, and the two lines meet

A `category` axis spaces points evenly whatever dates they carry, so ninety
daily history points beside sixty daily forecast points came out compressed —
the past appeared to happen faster than the future. Every series now carries
`[date, value]` pairs on an `xAxis.type = "time"`. The prediction is prepended
with the last historical point so the solid and dashed lines meet at today
instead of leaving a day-wide gap.

### The horizon is the horizon

`predicted_balance_30d` answers about day 30 whatever horizon was asked for.
`forecast_kpis` reads the **last** forecast point, so a 90-day request gets a
90-day answer, and the figure carries the date under it. The service property
is left alone — it has other callers.

### The figures cannot disagree with the picture

`forecast_kpis(result)` takes the same `ForecastResult` the chart is drawn
from — after `apply_preset` and `apply_scenarios` — so a what-if that lifts
the line lifts the figures by exactly as much, and the interval that moved
with it leaves the ± unchanged. Recomputing them from the raw forecast was
the prototype's mistake.

### One timer, and a dialog that outlives its own Save

Two NiceGUI traps, both found by the e2e:

- A `ui.timer` created inside an event handler belongs to the handler's
  ambient slot. Save redraws the scenario chips — including the chip whose
  click opened the dialog — so by the time the timer was constructed its
  parent was gone (`The parent element this slot belongs to has been
  deleted`). There is one debounce timer now, built with the page and armed
  by `activate()`.
- The add-scenario dialog had the same problem: built inside the chip row, it
  was deleted halfway through its own handler. It is built once with the page
  and reset on open.

### `data-kpi` on each figure

Three of the four KPI titles — Predicted, Change, Confidence — are words that
also appear in the chart legend and in the upcoming-14 table, so neither a
reader's eye nor a test can find *the figure* by its text. Each card names
itself.

### e2e: the page remembers the account

`forecast_account` and `forecast_horizon` are new persisted keys, which the
plan asks for. The e2e suite shares one browser session, so "All Accounts is
the default" stopped being true once another test picked an account:
`KAL-FCT-003` selects it explicitly, which is what the scenario says anyway.
The scenario test removes its own scenario at the end for the same reason —
and that exercises removal.

### KAL-FCT-011 is an e2e, not a unit test

Scope says "@automated, unit on the KPI helper", but `scripts/spec_coverage.py`
only scans `tests/e2e` and `tests/integration`, so a `Covers:` in
`tests/unit` counts for nothing. The rule is unit-tested either way
(`TestForecastKpis`); the scenario is carried by an e2e that adds a windfall
through the dialog and asserts the predicted and change figures move by its
amount, then takes it away again.

### Scenarios reworded, not re-scoped

`KAL-FCT-001`, `002`, `003` and `007` each had a "When I click Run forecast"
step that the page no longer has; they now describe a page that has already
run. `KAL-FCT-009` describes a footnote rather than the amber banner. The
banner's keys (`fallback_banner`, `click_run`, `run`, `running`,
`current_balance`, `predicted_30`, `change_30`) are gone from both locales
rather than left behind as cruft.

### New tokens

`--k-accent-soft` (`#F4E3D5` / `#3A2E24`) behind the KPI icons, replacing the
per-view `bg-blue-500/10 text-blue-600` triplets, and `.k-skeleton` so the
wait looks like this app rather than Quasar's grey. Both in `theme.py` with
the rest.

### Not done

The `[manual]` criterion — `/forecast` on seed data compared to artboard `3a`
in light and dark, with and without Prophet — is the owner's visual pass.
This repo's dev environment has no Prophet, so the stale-then-Re-run branch
of open question 1 is exercised by reading, not by running: it is part of
that manual pass. Forecaster models, presets and scenario semantics are
untouched, as Scope says.
