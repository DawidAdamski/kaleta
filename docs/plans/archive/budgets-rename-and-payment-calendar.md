---
plan_id: budgets-rename-and-payment-calendar
title: Budgets rename + new Payment Calendar view
area: budgets
effort: large
status: archived
archived_at: 2026-04-22
roadmap_ref: ../roadmap.md#budgets
---

# Budgets rename + new Payment Calendar view

## Intent

"Budgets" as a page title is overloaded — it covers both planned
income/expense allocation *and* the timing of bills. Split the
concerns: keep **Budgets** for allocation, introduce **Payment
Calendar** for the timing view.

## Scope

- Rename left-nav "Budgets" → "Budgets" stays; but the current
  "Planned Transactions" view is promoted to a first-class
  **Payment Calendar** with its own nav entry and icon.
- Payment Calendar view:
  - Month grid: each cell shows planned inflow/outflow totals.
  - Clicking a cell opens a slide-over with the day's planned items.
  - Ability to add a planned transaction directly on a day.
  - Overdue items pinned to the top of the sidebar panel regardless
    of selected day.
- Budgets view stays focused on allocation (planning + realization
  tab).
- Cross-link: Budgets view shows a "See upcoming bills →" link to
  the Payment Calendar; Payment Calendar shows "See budget coverage
  →" back.

Out of scope:
- Changing the underlying `PlannedTransaction` model beyond any
  fields needed for calendar rendering.
- Bill reminders via notifications — covered under the monthly
  readiness plan.

## Acceptance criteria

- New nav item "Payment Calendar" routes to the new view.
- Month grid renders with per-day planned totals that match the
  sidebar list.
- Drag-to-reschedule on the calendar cell updates the planned date
  with an undo toast.
- Budgets view no longer lists planned transactions inline.

## Touchpoints

- `src/kaleta/views/layout.py` — new nav entry.
- `src/kaleta/views/planned_transactions.py` → split into the new
  `src/kaleta/views/payment_calendar.py` (month grid) and a legacy
  redirect.
- `src/kaleta/services/planned_transaction_service.py` — add
  `grid_for_month` returning the per-day aggregates.
- `src/kaleta/views/budgets.py` — remove the inlined planned list,
  add the "See upcoming bills →" link.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Should the Payment Calendar host unbudgeted bills too (anything
  `PlannedTransaction`), or filter to "bills" only? v1: everything
  planned; categorisation is the user's concern.
- Week view as well as month view? Ship month-only in v1; week
  later.

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-22.

| SHA | Author | Date | Message |
|---|---|---|---|
| `2a70bf8` | Dawid | 2026-04-22 | feat(calendar): add Payment Calendar month-grid view |

**Files changed:**
- src/kaleta/services/planned_transaction_service.py (added `grid_for_month`, `DayAggregate`, `MonthGrid`)
- src/kaleta/views/payment_calendar.py (new)
- src/kaleta/main.py
- src/kaleta/views/layout.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- tests/unit/services/test_planned_transaction_service.py (9 new tests, 35 total)

**What shipped:** Month-grid at `/payment-calendar` with a KPI row (inflow / outflow / net / overdue), Mon–Sun grid with per-day inflow/outflow badges, today highlight, prev/next/Today navigation, quick-add dialog pre-filled with the selected day, right-side day drawer listing occurrences with an Add-on-this-day shortcut, and overdue items (prior 30 days) pinned in the drawer. Nav updated to `calendar_month` → `/payment-calendar`; the `/planned` flat table is still reachable via a "List view" button.

**Partial coverage:** Drag-to-reschedule is **deferred** to a future follow-up plan. The plan called for drag-to-move on the calendar cell; we shipped the calendar without this interaction to keep scope tight (user-approved tradeoff).
