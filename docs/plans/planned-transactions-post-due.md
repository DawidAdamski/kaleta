---
plan_id: planned-transactions-post-due
title: Planned transactions — post due occurrences to the ledger
area: planned-transactions / payment-calendar
effort: medium
status: draft
roadmap_ref: ../roadmap.md#transactions
source: audit-production-readiness.md#6-planned-transactions-are-never-posted
---

# Planned transactions — post due occurrences to the ledger

## Intent

Payment Calendar computes occurrences and an overdue bucket, but
nothing converts a due planned transaction into a real ledger row.
Daily-run consequence: recurring bills must be re-entered or
re-imported. Add an explicit **"post due"** path (one-click and
bulk), then an **opt-in** auto-post on app start. Full background
scheduling is unnecessary for a locally run app.

## Scope

- `PlannedTransactionService`:
  - `post_occurrence(planned_id, occurrence_date) → Transaction`
    (and transfer pair when type is transfer)
  - `post_due(as_of: date | None = today) → list[Transaction]` —
    all overdue / due-today active occurrences not yet posted
  - Idempotency: do not double-post the same planned + date
    (track via link field, occurrence marker, or lookup of existing
    posted rows — pick one approach in implementation notes)
- UI:
  - Payment Calendar overdue bucket: per-row **"Post"** + **"Post
    all due"**
  - Dashboard upcoming-planned widget: one-click post per item
  - Planned Transactions page: post next / selected occurrence
- Settings → Features: **"Auto-post due planned transactions on
  startup"** (default **off**)
- Startup hook: if enabled, call `post_due` and notify count posted
- New BDD under Planned Transactions: `KAL-PLN-015`+ (post one,
  post all due, idempotent re-post, opt-in auto-post)

This plan **owns** "convert to actual / post occurrence". The
related draft [`transactions-upcoming-planned.md`](transactions-upcoming-planned.md)
covers **visibility** of upcoming rows in the Transactions list
only; any post button there must call this service and is deferred
until this plan ships (or is a thin follow-up).

### Not in scope

- Full OS-level scheduler / cron daemon
- Matching bank-import rows to planned occurrences (reconcile)
- Skipping / snoozing UX beyond what already exists
- Inline "upcoming" merge on `/transactions` (separate plan)

## Acceptance criteria

- `uv run pytest tests/unit/services/test_planned_transaction_service.py -q`
- `grep -E 'KAL-PLN-01[5-9]|KAL-PLN-02' docs/bdd.md | grep -q .`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `[manual]` Overdue item on Payment Calendar posts a matching
  expense/income/transfer and disappears from the overdue bucket
  (or moves to posted state) after refresh.

## Touchpoints

- `src/kaleta/services/planned_transaction_service.py`
- `src/kaleta/services/transaction_service.py` (create path reuse)
- `src/kaleta/views/payment_calendar.py`
- `src/kaleta/views/dashboard_widgets/upcoming_planned.py`
- `src/kaleta/views/planned_transactions.py`
- `src/kaleta/views/settings/` — Features toggle
- `src/kaleta/main.py` — optional startup auto-post
- `src/kaleta/models/` — only if a posting link / marker column
  is required (prefer minimal schema change)
- `src/kaleta/i18n/locales/{en,pl}.json`
- `docs/bdd.md` — `KAL-PLN-015+`
- `tests/unit/services/test_planned_transaction_service.py`
- `tests/e2e/` — post-due happy path when views change

## Open questions

1. **Idempotency store** — dedicated `posted_occurrences` table vs
   `transactions.planned_transaction_id` + date uniqueness.
   Default preference: FK + unique constraint on
   `(planned_transaction_id, date)` if schema allows.
2. **Partial amounts / edits before post** — v1 posts template
   amount as-is; edit-after-post is normal transaction edit.

## Implementation notes

_Filled in as work progresses._

Source finding: `audit-production-readiness` P1.6. One plan = one
branch = one PR.
