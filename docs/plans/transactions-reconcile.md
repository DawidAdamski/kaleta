---
plan_id: transactions-reconcile
title: Transactions — reconcile flow
area: transactions
effort: medium
status: draft
roadmap_ref: ../roadmap.md#transactions
---

# Transactions — reconcile flow

## Intent

Users should be able to confirm that a set of transactions matches
their bank statement and mark them as reconciled. Reconciled rows are
locked against accidental edits.

## Scope

- Add a `reconciled_at` timestamp column on `Transaction`.
- "Reconcile" mode on the Transactions view: multi-select rows, type
  the target ending balance, system confirms match and stamps
  `reconciled_at = now()` on the selected set.
- Reconciled rows get a locked visual state (small lock icon, greyed
  amount) and a guard in the service layer preventing edit/delete
  unless the user first "unlocks".
- Unlock = clear `reconciled_at` for that row only; requires a
  confirmation dialog.

Out of scope:
- Auto-matching against an imported statement file — deferred.
- Partial reconciliation across accounts.

## Acceptance criteria

- Selecting rows + entering an ending balance that matches (within a
  tolerance of 0.01) sets `reconciled_at` for all selected rows.
- Edits to a reconciled row are rejected with a clear error unless
  the user unlocks first.
- Filter "Reconciled: yes/no/any" works on the Transactions view.
- Reconciliation state survives edits to other fields of adjacent
  rows.

## Touchpoints

- Alembic migration adding `reconciled_at TIMESTAMP NULL`.
- `src/kaleta/models/transaction.py`.
- `src/kaleta/schemas/transaction.py` — add field + guards.
- `src/kaleta/services/transaction_service.py` — reconcile method,
  edit guards, unlock method.
- `src/kaleta/views/transactions.py` — reconcile toolbar, lock icon,
  filter.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Tolerance: 0.01 (one cent) or exact? v1: exact. Revisit on feedback.
- Should the ledger offer an auto-suggested "reconcile up to date X"
  batch? Out of scope for v1.

## Implementation notes

_(filled as work progresses)_
