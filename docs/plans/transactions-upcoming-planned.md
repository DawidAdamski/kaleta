---
plan_id: transactions-upcoming-planned
title: Transactions — show upcoming planned items (next N days)
area: transactions
effort: medium
roadmap_ref: ../roadmap.md#transactions
status: draft
---

# Transactions — show upcoming planned items (next N days)

## Intent

The Transactions list shows past actuals only. Users wanting a
quick "what's coming" view have to switch to /payment-calendar
or /planned-transactions. Render upcoming `PlannedTransaction`
occurrences for the next **N days** (user-configurable, default
**7**, alternative **30**) inline with the actuals, visually
distinguished as planned, so the user gets a single
chronological feed of past + near-future cashflow without
leaving the page.

## Scope

- **Settings — new field** in the Settings → Features tab
  (`views/settings.py`):
  - Label: "Show upcoming planned transactions". Options:
    `Off / 7 days / 30 days`. Default: `7 days`.
  - Persisted in `app.storage.user["transactions_upcoming_days"]`
    (NiceGUI per-user storage; matches existing pattern of
    other Features-tab toggles).
- **View — Transactions list** (`views/transactions.py`):
  - On page load, read the setting; if non-zero, call
    `PlannedTransactionService.get_occurrences(today,
    today + N days)` and merge into the rendered rows.
  - Insert occurrences at the top of the list (newest-first
    ordering already used; planned occurrences have future
    dates so they naturally land at the top after the sort).
  - Mark each planned row visually:
    - Faded / italic typography (Tailwind `italic
      text-slate-500` or a `.k-planned-row` class).
    - Right-side `ui.chip(t("transactions.planned_chip"),
      icon="schedule")` so the user can tell.
    - Date column shows the relative phrase
      ("In 3 days · Wed 14") in addition to the raw date.
  - Clicking a planned row opens the PlannedTransaction
    detail dialog (existing `/planned-transactions` edit
    flow), not the Transaction edit dialog.
  - The "convert to actual" action (already on the planned
    transactions page) is also available from a row-level
    button so the user can mark a planned row as posted
    without leaving Transactions.
- **Sorting / filtering** — the existing filter bar (date
  range, account, category, type, description) applies to
  planned occurrences as well. Account / category / type /
  description filters: re-use the same predicates against
  `PlannedOccurrence`. Date-range filter: clip the upcoming
  window to the user's chosen range.
- **i18n** — `transactions.planned_chip`,
  `transactions.upcoming_section_label` (if a section header
  is preferred over inline interleaving),
  `transactions.upcoming_in_days_label`,
  `settings.show_upcoming`, `settings.show_upcoming_hint`,
  `settings.show_upcoming_off`, `settings.show_upcoming_7`,
  `settings.show_upcoming_30`.
- **Tests** —
  - Unit: helper that merges actuals + occurrences and
    re-sorts.
  - Integration: with a planned monthly rent due on day 5,
    `today = day 3`, `N=7` shows 1 planned row; `N=30` may
    show 2 (this month's and next month's, depending on
    calendar).
  - Settings round-trip: change setting, reload, verify
    storage persistence.

Out of scope:
- Editing the planned-transaction template from the
  Transactions list. The row click opens the detail dialog
  in read-only "next occurrence" mode.
- Auto-hiding planned rows once their date passes (the
  service already filters by `today` so this is automatic).
- Confirming a posted occurrence as "skipped" — that's
  handled on the planned-transactions page.
- Showing planned rows in the CSV export.

## Acceptance criteria

- Setting `transactions_upcoming_days = 7`: a planned weekly
  expense due in 3 days appears as a row in /transactions,
  italicised, with a `schedule` chip and the date "In 3 days".
- Setting set to `0` (Off): no upcoming rows appear; the
  page renders identically to today.
- Filtering by account hides planned rows from other
  accounts.
- Clicking a planned row opens the planned-transaction
  edit dialog, not the regular transaction dialog.
- A "Convert to actual" button on the row creates a real
  `Transaction`, removes that occurrence from the upcoming
  list (next occurrence still shows for recurring plans),
  and refreshes the row.

## Touchpoints

- `src/kaleta/views/settings.py` — Features tab gains the
  new tri-state toggle.
- `src/kaleta/views/transactions.py` — fetch + merge upcoming
  occurrences; row rendering tweaks; row click handler.
- `src/kaleta/services/planned_transaction_service.py` —
  reuse `get_occurrences()`; possibly add a
  `convert_to_actual(occurrence_date, planned_id)` helper.
- `src/kaleta/i18n/locales/{en,pl}.json` — new keys.
- `tests/unit/services/test_planned_transaction_service.py`
  and a new
  `tests/integration/views/test_transactions_upcoming.py`.

## Open questions

1. **Inline merge vs separate "Upcoming" section?** Default:
   **inline merge** — the user thinks chronologically; a
   separate section forces a context switch. Visual fade +
   chip is enough to disambiguate.
2. **Default value** — `7 days` strikes a balance: long enough
   to plan the week, short enough not to pollute the list.
3. **Server-side vs client-side merge?** Server-side. Generating
   occurrences in Python keeps the existing service and lets
   the API return them too.
4. **Group separators** — the existing month/week separator
   logic should treat planned rows as ordinary rows for the
   purpose of grouping; verify in tests.

## Implementation notes
_Filled in as work progresses._
