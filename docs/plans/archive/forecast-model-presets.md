---
plan_id: forecast-model-presets
title: Forecast — model presets + scenario toggles
area: forecast
effort: medium
status: archived
archived_at: 2026-04-22
roadmap_ref: ../roadmap.md#forecast
---

# Forecast — model presets + scenario toggles

## Intent

Prophet is powerful but opaque. Give the user 3 readable presets
("conservative", "baseline", "optimistic") plus scenario toggles that
simulate common life events — without exposing Prophet knobs.

## Scope

- Preset selector on the Forecast view (segmented control):
  - conservative — dampens positive seasonality, widens the lower
    bound.
  - baseline — current behaviour.
  - optimistic — symmetric opposite of conservative.
- Scenario toggles (stack multiple): "+500 monthly income",
  "−300 monthly expense", "one-off bonus next month", "one-off
  expense in 30 days".
- Scenarios adjust the forecast ex-post (add/subtract a constant to
  the projected series); they do NOT retrain Prophet.
- Show the baseline faded in grey as a reference band when any
  scenario is active.

Out of scope:
- User-saved custom scenarios — first-party only in v1.
- Exposing Prophet seasonalities / changepoints directly.

## Acceptance criteria

- Switching preset re-renders the forecast within 500ms from cache.
- Applying a scenario shifts the projected line by the expected
  constant; totals update accordingly.
- Clearing all scenarios restores the baseline cleanly.
- Preset + scenario selections persist per user between sessions.

## Touchpoints

- `src/kaleta/services/forecast_service.py` — add preset logic and
  scenario adjustment layer (pure add/subtract, no retraining).
- `src/kaleta/views/forecast.py` — preset segmented control, scenario
  chips, baseline-band rendering.
- `src/kaleta/schemas/forecast.py` — request schema includes preset
  + active scenarios.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Conservative/optimistic deltas: what percentile width feels right?
  Start with ±10% of the forecast mean; adjust after dogfooding.
- Should the scenario list be pluggable (plugin style)? Not in v1.

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-22.

| SHA | Author | Date | Message |
|---|---|---|---|
| `4317f40` | Dawid | 2026-04-22 | feat: dashboard command center, reports library, forecast presets, and plan-driven features |

**Files changed:**
- src/kaleta/services/forecast_service.py
- src/kaleta/views/forecast.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- tests/unit/services/test_forecast_service.py

**Notes:** Shipped as `ForecastPreset` StrEnum (conservative/baseline/optimistic) + pure `apply_preset` helper, plus `ScenarioShift` dataclass with stacked deltas via `apply_scenarios`. Forecast view gained preset toggle, scenario chips + add-dialog, and a baseline reference line. 11 unit tests exhaustively cover both pure helpers. Schema changes landed inside `forecast_service.py` rather than a separate `schemas/forecast.py` file.
