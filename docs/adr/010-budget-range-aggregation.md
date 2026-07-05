---
adr_id: "010"
title: "Budget Range Aggregation"
status: accepted
---

# ADR-10: Budget Range Aggregation

- **Decision**: `BudgetService.range_summary(start, end)` aggregates budget rows
  across multiple months using a scalar month key (`year * 12 + month`).
- **Rationale**: Budgets are stored per-month. To display multi-month ranges
  (quarter, year, last N days), budget amounts must be summed across all months that
  fall within the range, while actuals are filtered by exact transaction dates.
- **Consequence**: The UI period selector supports 10 presets (This Month → Last 5 Years).
  `monthly_summary()` now delegates to `range_summary()` to avoid duplication.
