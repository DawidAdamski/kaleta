---
plan_id: gifts-mark-bought
title: Gifts — mark a gift bought by linking the transaction that paid for it
area: models + services + views (gifts)
effort: medium
status: archived
archived_at: 2026-10-19
roadmap_ref: ../../roadmap.md
---

# Gifts — mark a gift bought by linking the transaction that paid for it

## Intent
Dogfooding #21 / GitHub #11, #21 — slice 3 (final) of Gift Planning (BDD
`KAL-GFT-003`). Slices 1–2 built the gift list, its yearly total and its line
on the irregular fund. This slice closes the loop: once you actually buy a
gift, you link the ledger transaction that paid for it, and the gift is marked
**bought** with its **actual cost** — so planned (200.00) and actual (189.99)
sit side by side and you can see where you came in over or under.

## Scope
Slice 3 = `KAL-GFT-003` only: link a transaction to a gift, mark it bought.

- **`Transaction.gift_id`** (`src/kaleta/models/transaction.py`): a new nullable
  FK → `gifts.id`, `ondelete=SET NULL`, indexed — mirrors the existing
  `irregular_item_id` link. A gift is "bought" when ≥1 transaction points at it;
  its actual cost is the sum of those transactions' amounts. `gift_id` and
  `amount` are plain columns, so this is grouped in SQL (unlike the encrypted
  person/occasion).
- **Alembic migration** adding `transactions.gift_id` (`down_revision` = current
  head `c9c34c5fcfe3`), with the index and the SET-NULL FK.
- **Schema** (`src/kaleta/schemas/gift.py`): `GiftResponse` gains
  `bought: bool = False` and `actual_cost: Decimal | None = None`, filled by the
  service.
- **Service** (`src/kaleta/services/gift_service.py`):
  - `link_transaction(gift_id, transaction_id)` — validates both exist
    (`NotFoundError`) and the transaction is an EXPENSE (`ValidationError`),
    then sets `tx.gift_id`.
  - `mark_not_bought(gift_id)` — clears `gift_id` on every transaction linked to
    the gift (undo).
  - `buyable_transactions(limit)` — recent EXPENSE transactions not yet linked
    to any gift, for the picker (via `TransactionService.list`).
  - `summary()` / the gift responses compute `bought` / `actual_cost` from one
    grouped query over `Transaction.gift_id`.
- **View** (`src/kaleta/views/gifts.py`): on each gift row, when not bought a
  "Mark as bought" button opens a dialog listing recent expense transactions
  (date · description · amount) to pick from; when bought, a "bought" badge, the
  actual cost next to the planned amount, and a "Mark not bought" undo.
- **i18n**: a few `gifts.*` keys in `en.json` + `pl.json` (same keys).
- **Tests**: service coverage in `tests/unit/services/test_gift_service.py`
  (link → bought + actual cost; a second linked transaction sums; unlink;
  not-found; non-expense rejected); e2e `KAL-GFT-003` in
  `tests/e2e/test_gifts.py` (seed a gift + a 189.99 expense, link in the UI,
  assert bought + 189.99).
- **BDD**: retag `KAL-GFT-003` `@planned` → `@automated`.

**Not in scope (binding):**
- No change to the irregular fund line (slice 2) — a bought gift still counts
  toward the yearly gift total here; reconciling planned-vs-actual in the fund
  total is a separate concern, not this slice.
- The "mark bought" flow **links an existing** ledger transaction; it does not
  create a transaction, and does not change the gift's planned `amount`.
- No category/payee defaulting, no multi-transaction management UI beyond the
  derived sum, no REST `api/v1` route.

## Acceptance criteria
- `uv run pytest tests/unit/services/test_gift_service.py -q`
- `uv run pytest tests/e2e/test_gifts.py -q`
- `grep -q "KAL-GFT-003 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

Fail-on-old: the new service assertions read `gift.bought` / `gift.actual_cost`
and call `link_transaction`, none of which exist before this slice; the e2e
links a transaction in a UI the current page does not have. Expected values are
the BDD literals (planned 200.00, actual cost 189.99).

## Touchpoints
- `src/kaleta/models/transaction.py`
- `alembic/versions/<hexid>_add_transaction_gift_id.py`
- `src/kaleta/schemas/gift.py`
- `src/kaleta/services/gift_service.py`
- `src/kaleta/views/gifts.py`
- `src/kaleta/i18n/locales/en.json`
- `src/kaleta/i18n/locales/pl.json`
- `tests/unit/services/test_gift_service.py`
- `tests/e2e/test_gifts.py`
- `tests/e2e/seed_helpers.py`
- `docs/bdd.md`

## Open questions
- None blocking. Resolved in decisions below.

## Implementation notes
- **Decision — bought/actual_cost are derived, not stored.** Like the irregular
  fund's payments, the link lives on the transaction (`Transaction.gift_id`) and
  the gift's state is computed: `bought` = a linked transaction exists,
  `actual_cost` = `SUM(amount)` of linked transactions. One source of truth, no
  stored flag to drift, and it handles a gift paid across several transactions
  without extra rules. The BDD's single 189.99 transaction is the common case.
- **Decision — link an existing transaction, don't create one.** The BDD says
  "link a 189.99 transaction", so the flow picks from the ledger; marking bought
  never creates ledger rows and never edits the planned amount.
- No new table, so the seeded-table guards are untouched; `Transaction` is
  already in `DataService._CLEARED_MODELS`, and clearing transactions nulls the
  new FK. The backup service is metadata-driven, so the new column rides along.
- The example-data seeder is left as-is: seeded gifts stay "planned" (unbought).
  Marking bought is a user action, not part of the demo dataset — so no seeder
  or seeder-guard change.
- **Deleting a linked transaction** reverts the gift to unbought with no extra
  bookkeeping: `bought` / `actual_cost` are a live `SUM` over
  `Transaction.gift_id`, and the FK is `ondelete=SET NULL`, so the row simply
  drops out of the sum. Deleting a *gift* nulls the transactions' `gift_id`
  rather than touching the ledger. A unit test pins the transaction-delete case.
- `buyable_transactions` filters `gift_id IS NULL` **in the query** (not after a
  `limit`), so an already-bought expense never uses up a picker slot and hides
  an older free one (review finding). It queries `Transaction` directly rather
  than through `TransactionService`, so there is no service-to-service call.
- Two helpers beyond the original touchpoint list: `GiftService.get_response`
  (one gift with its bought state, for the unit tests and a single-row caller)
  and the e2e `delete_transaction` helper (ledger cleanup, rerun-safe). Both
  small and test-driven.

## Implementation

Landed on 2026-10-19 (PR #285).

| SHA | Author | Date | Message |
|---|---|---|---|
| `e13fd03` | Dawid Adamski | 2026-10-19 | Merge pull request #285 from DawidAdamski/feat/gifts-mark-bought |

**Files changed:**
- alembic/versions/e9ecbe7dd5b0_add_transaction_gift_id.py
- docs/bdd.md
- docs/plans/gifts-mark-bought.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/models/transaction.py
- src/kaleta/schemas/gift.py
- src/kaleta/services/gift_service.py
- src/kaleta/views/gifts.py
- tests/e2e/seed_helpers.py
- tests/e2e/test_gifts.py
- tests/unit/services/test_gift_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
