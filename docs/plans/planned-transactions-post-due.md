---
plan_id: planned-transactions-post-due
title: Planned transactions — post due occurrences
area: planned-transactions
effort: medium
roadmap_ref: ../roadmap.md#transactions
status: in-progress
source: ../plans/audit-production-readiness.md#6-planned-transactions-are-never-posted
---

# Planned transactions — post due occurrences

## Intent

Payment Calendar computes occurrences and an overdue bucket, but nothing
converts a due planned transaction into a real ledger row. Users must
re-enter recurring bills manually. Add explicit post actions (single
occurrence and post-all-due) plus an opt-in auto-post on session start so
the ledger stays in sync with the calendar without an OS cron.

## Scope

- **Service** — `PlannedTransactionService.post_occurrence(planned_id, date)`
  and `post_due(as_of=today, lookback_days=…)` — both **idempotent**.
- **Schema** — `Transaction.planned_transaction_id` FK + unique
  `(planned_transaction_id, date)` so re-posting the same occurrence is a
  no-op (returns the existing row).
- **UI**
  - Payment Calendar: Post on overdue / past-due rows; **Post all due**
    toolbar action.
  - Dashboard `upcoming_planned` widget: one-click Post on due rows.
  - Planned Transactions list: post action per row (posts due
    occurrences for that plan).
- **Settings → Features** — toggle “Auto-post due planned transactions
  on start” (default **OFF**); session-start hook runs `post_due` once
  when enabled.
- **BDD** — new `KAL-PLN-015+` scenarios; unit/e2e coverage with
  `Covers:` docstrings.

Out of scope:

- OS cron / background scheduler beyond session-start.
- Import-reconcile matching of bank rows to planned occurrences.
- Upcoming planned merge on `/transactions`
  (`transactions-upcoming-planned` plan).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_planned_transaction_service.py -q -k post`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `[manual]` Payment Calendar overdue row Post creates a transaction and
  removes the item from the overdue bucket after refresh.
- `[manual]` Features toggle default is OFF; with toggle ON, first
  authenticated page load posts due occurrences once per session.

## Touchpoints

- `src/kaleta/models/transaction.py` — FK + unique constraint
- `alembic/versions/` — migration
- `src/kaleta/schemas/transaction.py` — optional `planned_transaction_id`
- `src/kaleta/services/planned_transaction_service.py` — post APIs
- `src/kaleta/views/payment_calendar.py`
- `src/kaleta/views/dashboard_widgets/upcoming_planned.py`
- `src/kaleta/views/planned_transactions.py`
- `src/kaleta/views/settings/features_tab.py` (+ constants)
- `src/kaleta/views/layout.py` — session-start auto-post hook
- `src/kaleta/i18n/locales/{en,pl}.json`
- `docs/bdd.md` — KAL-PLN-015+
- `tests/unit/services/test_planned_transaction_service.py`
- `tests/e2e/` — post-due coverage where practical

## Open questions

1. **Process startup vs session start?** NiceGUI `app.storage.user` is
   not available in `on_startup`. Auto-post runs once per authenticated
   session on first `page_layout` (equivalent for a local single-user
   app). Recorded in Implementation notes.

## Implementation notes

- **Idempotency**: `Transaction.planned_transaction_id` + unique
  `(planned_transaction_id, date)`. `post_occurrence` / `post_due` look up
  first; `IntegrityError` on race uses a SAVEPOINT (`begin_nested`) and
  returns the existing row.
- **exclude_posted**: `get_occurrences(..., exclude_posted=True)` used by
  Payment Calendar grid, overdue bucket, dashboard widget, and `post_due`.
  Forecast / monthly readiness keep the default (`False`).
- **Auto-post hook**: Features toggle
  `auto_post_due_on_startup` (default off). Process `on_startup` cannot read
  NiceGUI `app.storage.user`, so `page_layout` schedules
  `maybe_auto_post_due()` once per authenticated session via `ui.timer`.
- **Category-less plans**: posting inserts `Transaction` ORM rows directly
  (skips `TransactionCreate` category requirement) so optional planned
  categories still post.
- **Transfer plans**: still a single ledger leg (no destination account on
  the planned model); out of scope to invent a pair.
