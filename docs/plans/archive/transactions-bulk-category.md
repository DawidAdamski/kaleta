---
plan_id: transactions-bulk-category
title: Bulk change-category for selected transactions
area: transactions
effort: medium
status: archived
archived_at: 2026-10-15
roadmap_ref: ../../roadmap.md#transactions
---

# Bulk change-category for selected transactions

## Intent
Dogfooding #17: the ledger grew a multi-select bar (pair, delete, net total)
but no way to recategorise a batch. Recategorising is the most common cleanup
after an import — a handful of "Uncategorised" rows that are all groceries, or
a payee the rules missed. Selecting them and picking one category should move
them all in a single step.

## Scope
- **Service:** `TransactionService.set_category_bulk(ids, category_id) -> int`.
  Assigns one category to many rows and returns how many changed. The
  category's type must match every row's (an expense category cannot land on
  an income), and split rows carry a category per line — both are refused for
  the whole batch rather than applied in part, so the user is never left
  guessing which rows moved.
- **UI:** a "Change category" action on the selection bar
  (`table_actions.py`) opening a small dialog (`bulk_category_dialog.py`) with
  one category picker. The action is enabled only when the selection is a
  single assignable type with no splits (`assignable_category_type`); the
  picker then offers that type's categories. Applying keeps the reader's place
  (reuses `_refresh_keeping_place` from `transactions-keep-place-on-save`).
- **i18n:** `transactions.change_category*` and `transactions.category_assigned`
  in `en.json` / `pl.json`.

**Not in scope:**
- **#25** (select-all under search + grouping) was investigated in this slice
  (the chore note has the detail) but could not be reproduced as a correctness
  failure, so no behaviour change ships for it. It stays an open chore.
- Cross-type assignment (one pick for a mixed income+expense selection): the
  action is simply disabled there. A category is typed, so a single pick for a
  mixed batch has no correct meaning.

## Acceptance criteria
- `uv run pytest tests/unit/services/test_transaction_service.py -q -k SetCategoryBulk`
- `uv run pytest tests/unit/views/test_bulk_category.py -q`
- `uv run pytest tests/e2e/test_transactions_bulk_category.py -q`
- `uv run lint-imports`
- `./scripts/verify.sh --e2e` green (views changed → e2e mandatory, rule 8).

## Implementation notes
- The service takes primitives (`list[int]`, `int`), matching the sibling
  `pair_selected_as_transfer`, rather than a one-off Pydantic schema.
- Type-match uses `TransactionType(category.type.value)` — `CategoryType` and
  `TransactionType` share the `"income"`/`"expense"` values.
- UI gating (`assignable_category_type`) is a pure function so it is unit-
  tested directly; it keeps the error paths in the service from ever being hit
  by the common flow, while the service still enforces them for the API.
- `table_actions.py` imports `assignable_category_type` from
  `bulk_category_dialog` — same view layer, import-linter clean.
- Stale ids are skipped silently: the returned count is the number of rows
  actually found, so a caller passing an id that no longer exists gets a
  smaller count, not an error. Acceptable for the UI (the selection only ever
  holds live rows); an API caller that needs strictness can compare the count
  it passed against the count returned.

## Implementation

Landed on 2026-10-15.

| SHA | Author | Date | Message |
|---|---|---|---|
| `d62b9d3` | Dawid Adamski | 2026-10-15 | Merge pull request #267 from DawidAdamski/feat/transactions-bulk-category |
| `8a48ec0` | Dawid (Ani) | 2026-10-15 | feat(transactions): bulk change-category for selected rows (#17) |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/transactions-bulk-category.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/services/transaction_service.py
- src/kaleta/views/transactions/bulk_category_dialog.py
- src/kaleta/views/transactions/page.py
- src/kaleta/views/transactions/table_actions.py
- tests/e2e/test_transactions_bulk_category.py
- tests/unit/services/test_transaction_service.py
- tests/unit/views/test_bulk_category.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `uv run pytest tests/unit/services/test_transaction_service.py -q -k SetCategoryBulk` | 0 |
| `uv run pytest tests/unit/views/test_bulk_category.py -q` | 0 |
| `uv run pytest tests/e2e/test_transactions_bulk_category.py -q` | 0 |
| `uv run lint-imports` | 0 |
| `./scripts/verify.sh --e2e` | 0 |

