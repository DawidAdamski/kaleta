---
adr_id: "030"
title: "Read-Only Cross-Panel Projection Layer"
status: accepted
---

# ADR-30: Read-Only Cross-Panel Projection Layer

- **Decision**: Introduce `WizardProjectionService` as a dedicated read-only service that normalises data from other wizard panels (planned transactions, subscriptions, loans, reserve funds) into monthly-equivalent projections. Budget Builder (`/wizard/budget-builder`) and Payment Calendar (`/payment-calendar`) consume these projections to surface "pulled" rows from sibling panels without storing them locally. Cross-links redirect users to the source panel for edits.
- **Rationale**: Each wizard panel already owns its data; duplicating that data into a second panel's storage would create synchronisation drift. A pure read layer avoids duplication: the projection is recomputed at render time from the authoritative source, so no sync is needed. Keeping the service stateless (no writes) means it carries no migration cost and is trivially testable in isolation.
- **Consequence**: `WizardProjectionService.get_budget_builder_sources(year)` returns a `BudgetBuilderProjection` (income, fixed, variable, reserves); `get_payment_calendar_sources(start, end)` returns a `PaymentCalendarProjection` (subscription_charges). Monthly-equivalent rules: subscriptions = `amount × 30 / cadence_days`; planned transactions use a frequency→multiplier table divided by interval; reserve funds use `target ÷ multiplier` (emergency) or `target ÷ 12`; loans use `LoanProfile.monthly_payment` directly. Yearly totals = pulled monthly × 12. Already-saved `YearlyPlan` snapshots are unaffected — they stay as-written; the projection is not back-filled. Pulled rows render as read-only in the UI (lock icon + source badge).
