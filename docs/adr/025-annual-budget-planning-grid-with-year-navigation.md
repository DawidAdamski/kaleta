---
adr_id: "025"
title: "Annual Budget Planning Grid with Year Navigation"
status: accepted
---

# ADR-25: Annual Budget Planning Grid with Year Navigation

- **Decision**: Add a `/budget-plan` view that displays a 12-column (month) × N-row (category) grid for a selected year. Each cell holds a budget target. A "Budget vs Actual" toggle overlays actual spending from `TransactionService`. Year-over-year comparison shows the previous year's values alongside the current year.
- **Rationale**: The existing budgets page covers period summaries but does not support planning an entire year at once or comparing years. A spreadsheet-style grid matches how users plan annual budgets and makes bulk entry (uniform amount, copy previous month) practical.
- **Consequence**: Budget targets are stored in the existing `Budget` model (one row per category per month). `BudgetService` already stores per-month rows; the new view reads and writes them in bulk. The "set uniform amount" and "copy previous month" actions are view-level conveniences that write multiple budget rows in a single service call. Negative budget values are rejected at the schema level.
