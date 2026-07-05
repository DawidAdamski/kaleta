---
adr_id: "022"
title: "Planned/Recurring Transactions as a First-Class Model"
status: accepted
---

# ADR-22: Planned/Recurring Transactions as a First-Class Model

- **Decision**: Introduce a `PlannedTransaction` model that stores name, type (income/expense/transfer), amount, account(s), optional category, frequency (`WEEKLY`, `MONTHLY`, `YEARLY`), start date, optional end date, optional occurrence limit, and an `is_active` flag.
- **Rationale**: Recurring cash flows (subscriptions, salaries, rent) are predictable and should be modelled explicitly rather than inferred from historical data. An explicit model allows the forecast service to inject future occurrences into the Prophet series and the transactions view to surface them as upcoming items before they are recorded.
- **Consequence**: `PlannedTransactionService` provides full CRUD and an `active_occurrences_between(start, end)` method used by both the transactions view (show-planned toggle) and `ForecastService`. Transfer-type planned transactions reference both a source and destination account. Inactive planned transactions are excluded from the forecast and from the upcoming transactions overlay. The view lives at `/planned`.
