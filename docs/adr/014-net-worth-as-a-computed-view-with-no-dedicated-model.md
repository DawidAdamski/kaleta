---
adr_id: "014"
title: "Net Worth as a Computed View with No Dedicated Model"
status: accepted
---

# ADR-14: Net Worth as a Computed View with No Dedicated Model

- **Decision**: Net worth data is computed entirely at query time by `NetWorthService.get_summary()`. No `NetWorth` or `Snapshot` ORM model is added. Historical monthly values are reconstructed by walking backwards from current account balances, subtracting each month's net income/expense (internal transfers excluded).
- **Rationale**: Storing pre-computed snapshots would require either a background job or hook into every transaction write to stay consistent. For a personal-scale dataset the retrospective reconstruction from existing `Account` and `Transaction` data is fast enough and eliminates a synchronisation concern entirely.
- **Consequence**: `NetWorthService` depends only on existing models and produces three pure-Python dataclasses (`AccountSnapshot`, `MonthlyNetWorth`, `NetWorthSummary`) — no new migration is required. Account classification (asset vs. liability) is derived from balance sign: positive balance = asset, negative balance = liability. The view at `/net-worth` renders summary cards, a 13-month ECharts line+area chart coloured by sign, and a side-by-side account breakdown table.
