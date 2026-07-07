---
plan_id: transactions-splits-integrity
title: Transaction splits — server-side integrity and split-aware reporting
area: transactions
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#transactions
---

# Transaction splits — server-side integrity and split-aware reporting

GitHub issue: [#? Transaction splits (KAL-SPL)](https://github.com/DawidAdamski/kaleta/issues)
BDD spec: [`docs/bdd.md` → Feature: Transaction Splits](../bdd.md#feature-transaction-splits) (KAL-SPL-001…004)

## Intent

Splits exist (model `TransactionSplit`, `split_editor.py`, create path,
e2e `test_add_edit_split_transaction`) but the feature is half-wired.
The point of splitting — "I bought groceries *and* alcohol in Lidl, and
I want to see the alcohol in reports" — currently silently fails:

1. **Splits are invisible in every aggregate.** Budget actuals
   (`budget_service.py` ~L596, L688, L725), report joins
   (`report_service.py` ~L749), and saved-report filters
   (`saved_report_service.py` ~L203, L287) group/filter on
   `Transaction.category_id` only. Split transactions have
   `category_id = NULL` (enforced by `TransactionCreate`), so **split
   money disappears from budget-vs-actual and category reports.**
2. **Monthly Readiness false positive.** Stage 1
   (`monthly_readiness_service.py` ~L96) counts `category_id IS NULL`
   as "uncategorised" without excluding `is_split = TRUE` — every
   split transaction blocks closing the month.
3. **Sum is enforced only in the UI.** `TransactionService.split_balance`
   drives the widget hint, but neither the schema nor the service
   rejects splits whose amounts don't sum to `Transaction.amount` —
   the API can create unbalanced splits.
4. **Splits cannot be edited.** `TransactionUpdate` has no `splits`
   field and `TransactionService.update` ignores splits, so once
   created, a split can only be deleted and re-entered.

No schema/migration work needed — the tables are already right.

## Scope

### PR 1 — server-side integrity (KAL-SPL-002, KAL-SPL-004)

- **Schema** (`src/kaleta/schemas/transaction.py`):
  - `TransactionCreate.validate_rules`: when `is_split`, require
    `sum(s.amount for s in splits) == amount` (Decimal-exact, both
    already `decimal_places=2`). Error message must state the
    remaining difference.
  - Add `splits: list[TransactionSplitCreate] | None = None` and
    `is_split: bool | None = None` to `TransactionUpdate`.
    Semantics: `None` = leave unchanged; a list = replace all split
    rows. Validate the sum against the *effective* post-update
    `amount` (updated amount if provided, else current — this check
    lives in the service, since the schema can't see current state).
- **Service** (`src/kaleta/services/transaction_service.py`):
  - `update()`: handle `splits` — delete-orphan replace on the
    relationship, set `is_split`, clear `category_id` when becoming
    split, and validate the sum invariant. Raise the domain error
    from `kaleta.exceptions` (follow the existing hierarchy; no bare
    `ValueError` — see AGENTS.md).
  - Amount edits on a split transaction without a matching `splits`
    payload must be rejected (would break the invariant).
- **View** (`src/kaleta/views/transactions/edit_dialog.py`): mount the
  existing `split_editor` in the edit dialog (it is add-only today);
  disable Save while unbalanced, same as add.
- **API**: no new routes — `PATCH /api/v1/transactions/{id}` gains
  split editing for free via the schema. Check `api/v1/transactions.py`
  passes the field through.

### PR 2 — split-aware aggregation (KAL-SPL-003) + readiness fix

- **Single source of truth**: add one reusable selectable that
  normalises "categorised amount rows" from both plain and split
  transactions, e.g. in a new `src/kaleta/services/categorised_flows.py`
  (or wherever fits the layering — views must not touch it directly):

  ```
  non-split:  (t.category_id, t.amount, t.date, t.type, t.account_id, t.user_id)
  split:      (s.category_id, s.amount, t.date, t.type, t.account_id, t.user_id)
              from transaction_splits s JOIN transactions t, t.is_split = TRUE
  ```

  as a `union_all` subquery / CTE. All three call sites below consume
  it instead of touching `Transaction.category_id` directly.
- **Rewire**:
  - `budget_service.py` — the three actual-spending aggregates
    (~L596, ~L688, ~L725).
  - `report_service.py` — category joins in canned reports (~L749);
    audit the rest of the file for other `Transaction.category_id`
    aggregation.
  - `saved_report_service.py` — category filter (~L203) and join
    (~L287): a saved report filtered on category X must include split
    lines in X (and count only the split-line amount, not the parent
    total).
- **Monthly Readiness** (`monthly_readiness_service.py` stage 1):
  uncategorised = `(category_id IS NULL AND NOT is_split) OR
  (is_split AND EXISTS split row with category_id IS NULL)` — the
  second arm covers splits orphaned by category deletion
  (`ondelete="SET NULL"`).
- **Dashboard widgets**: check `views/dashboard_widgets/helpers.py`
  (already imports split helpers) and any per-category widget for the
  same blind spot; rewire onto the shared selectable if affected.

### Spec bookkeeping (either PR, whichever lands the behaviour)

- Retag in `docs/bdd.md`: KAL-SPL-001…004 `@planned` → `@automated`.
- Tests reference IDs in docstrings: `Covers: KAL-SPL-00x`.
  - KAL-SPL-001 is effectively covered by the existing e2e
    `test_add_edit_split_transaction` — add the ID to its `Covers:`.
  - KAL-SPL-002: unit tests on schema + service (reject unbalanced
    create/update via API path too — integration test).
  - KAL-SPL-003: unit test on budget actuals and saved-report filter
    with a seeded split (180 Groceries + 34.50 Alcohol ⇒ each bucket
    sees only its share).
  - KAL-SPL-004: e2e — edit an existing split, rebalance, save.
- Close the GitHub issue with `Closes #<n>` in the final PR.

Out of scope:
- CSV import producing splits (`bulk_create` stays split-free).
- Splitting transfers (validation already limits splits to
  income/expense).
- Split-level payees or tags.
- Forecast changes — forecast is account-level, unaffected.

## Implementation notes

### PR 1 (feat/splits-integrity)
- `TransactionCreate` rejects unbalanced splits at schema validation;
  `TransactionService._validate_split_sum` enforces the same invariant on
  update when `splits` is provided.
- `TransactionUpdate.splits` replaces all rows (delete-orphan via
  `transaction.splits.clear()` + append).
- Amount-only edits on an existing split transaction are rejected unless
  `splits` is included in the same request.
- Edit dialog mounts `split_editor` for split transactions; Save is disabled
  while lines are unbalanced.

## Acceptance criteria

- `uv run python scripts/spec_coverage.py`
- `grep -qE "KAL-SPL-001 @(automated|manual)" docs/bdd.md`
- `grep -qE "KAL-SPL-002 @(automated|manual)" docs/bdd.md`
- `grep -qE "KAL-SPL-003 @(automated|manual)" docs/bdd.md`
- `grep -qE "KAL-SPL-004 @(automated|manual)" docs/bdd.md`
- `uv run pytest tests/unit/services/test_transaction_service.py -q`
- `uv run pytest tests/unit/services/test_budget_service.py -q`
- `uv run pytest tests/integration -q`
- `bash scripts/verify.sh`
- [manual] Split 214.50 into 180.00 + 34.50 in the UI; Budgets
  "vs actual" and the category report show 34.50 under Alcohol, and
  Monthly Readiness stage 1 does not flag the transaction.
