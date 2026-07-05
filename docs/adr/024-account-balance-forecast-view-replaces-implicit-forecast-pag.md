---
adr_id: "024"
title: "Account Balance Forecast View Replaces Implicit Forecast Page"
status: accepted
---

# ADR-24: Account Balance Forecast View Replaces Implicit Forecast Page

- **Decision**: Rename and expand the existing forecast view to a dedicated `/forecast` page that accepts per-account or multi-account selection, a configurable horizon, and a "include planned transactions" toggle. A zero-balance alert is shown when the predicted balance crosses zero within the horizon.
- **Rationale**: The original forecast was a single-account, fixed-horizon summary. Users need to combine accounts, tune the horizon, and understand interactions with planned transactions. The zero-balance alert is a high-value early-warning signal that requires no extra data.
- **Consequence**: `ForecastService` gains a `forecast_balance(account_ids, horizon_days, include_planned)` method that queries daily balance series for the selected accounts, optionally prepends planned-transaction occurrences, and runs Prophet in a thread pool. Individual account series are returned as secondary chart lines alongside the combined total. If Prophet receives fewer than 90 data points it returns a warning rather than a chart.
