---
plan_id: transactions-type-labels-i18n
title: Transactions — type column shows raw enum values instead of translations
area: transactions
effort: small
status: archived
archived_at: 2026-08-11
roadmap_ref: ../roadmap.md#transactions
---

# Transactions — translate the type column (and other raw enum renders)

## Intent

Dogfooding bug: *"W panelu transakcji typ jest napisany po angielsku,
mimo że jest ustawione wyświetlanie po polsku."* The Type column in the
transactions table shows `expense` / `income` / `transfer` — the raw
enum values — while the rest of the page is correctly translated.

## Root cause

- The shared transaction table renders the raw row field:
  `views/components/transaction_table.py:103` —
  `'<q-td key="type" :props="props">{{ props.row.type }}</q-td>'` —
  and the row dicts carry `tx.type.value` (English enum value).
- Translations already exist and are used elsewhere on the same page:
  the type **filter** (`transactions/page.py:218`) and the add/edit
  **dialogs** build options with
  `{tx.value: t(f"common.{tx.value}")}`, and `common.income/expense/
  transfer` have pl values (Przychód / Wydatek / Przelew). Only the
  table cell bypasses i18n.
- Same pattern in the **import preview** table:
  `import_service.build_preview_table_rows()` puts the raw
  `row_type` into the `type` field, rendered untranslated in
  `views/import_view/preview_section.py`.

## Scope

- **Row-build change, not template lookup**: add a `type_label` field
  (`t(f"common.{tx.type.value}")`) wherever transaction-table row dicts
  are built, and render `{{ props.row.type_label }}` in the type cell.
  **Keep the raw `type` field untouched** — the amount-colouring slot
  (`views/components/amount_label.py`, `amount_body_cell_slot`) keys
  its income/expense/transfer colours off `props.row.type`; changing
  its values would silently break semantic colours.
- Apply the same fix to the import preview rows
  (`build_preview_table_rows` gains a translated `type` display value
  or a parallel `type_label` — note this function lives in the service
  layer, which must NOT import the view i18n if that violates the
  import-linter contract; if it does, translate at the view boundary
  in `preview_section.py` instead).
- **Sweep for other raw enum renders** while in there:
  `grep -rn "props.row.type\|\.value" src/kaleta/views/` — check at
  least: planned-transactions table, subscriptions cadence, reports
  tables, account type chips. Fix the ones that render raw enum
  values; list the checked-and-clean ones in Implementation notes.
- **BDD**: add `KAL-TXN-006 @planned` (Feature: Manual Transaction
  Entry) — with the UI language set to Polish, the transactions table
  shows translated type values. Retag `@manual` or `@automated` when
  verified (an e2e asserting Polish strings needs the language toggled
  in test setup — if that plumbing is disproportionate, `@manual` is
  acceptable).

Out of scope: adding new translations (keys exist), language-switch
mechanics, translating enum values stored in the DB (they stay
English by design — display-layer concern only).

## Acceptance criteria

- `uv run pytest tests/unit -q`
- `grep -q "KAL-TXN-006" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` With Polish UI: transactions table shows
  Wydatek/Przychód/Przelew in the Type column; amount colours
  unchanged (expense red, income green, transfer neutral); import
  preview table also translated.

## Touchpoints

- `src/kaleta/views/components/transaction_table.py` (template + row
  build if local)
- `src/kaleta/views/transactions/page.py` (row dict construction)
- `src/kaleta/views/import_view/preview_section.py` and/or
  `src/kaleta/services/import_service.py` (`build_preview_table_rows`)
- `docs/bdd.md` (KAL-TXN-006)
- `tests/unit` (row-builder unit test asserting `type_label`)

## Open questions

1. Does any other consumer parse the table's visible type text (tests,
   e2e selectors)? Check `tests/e2e/test_transactions.py` for
   assertions on "expense"/"income" strings and update them to match
   labels or target the raw field.

## Implementation notes

- Services must not call `t()`: `kaleta.i18n` imports `nicegui`, which
  breaks the `services-no-ui` import-linter contract. Translation happens
  at the view boundary.
- `attach_type_labels()` in `views/components/transaction_table.py` adds
  `type_label` via `t(f"common.{type}")`; raw `type` kept for amount
  colouring. Called from `transactions/page.py` after `build_table_rows`.
- Import preview: same pattern in `preview_section.py` (column `field` →
  `type_label`; raw `type` kept for `amount_body_cell_slot`).
- Sweep results:
  - **Fixed**: transactions table, import preview, planned-transactions
    type badge, largest-transactions report (table + CSV).
  - **Clean** (raw `type` only for colouring / not displayed): dashboard
    recent_transactions, forecast planned-occurrences table.
  - **Clean** (already translated): accounts type chips, institutions
    type labels, net-worth account/asset types, subscriptions cadence.
- Open Q1: `tests/e2e/test_transactions.py` has no type-cell asserts.
  `tests/e2e/test_transfer_detection.py` did — updated to expect
  translated English labels (`Transfer`/`Expense`/`Income`).
- KAL-TXN-006 tagged `@manual` (Polish UI language toggle in e2e is
  disproportionate); unit test asserts Polish BDD literals via mocked
  `app.storage.user.language = "pl"`.
- Verify unblocker (unrelated flake): scoped KAL-CAT-011 locators to
  `main` so nav "Subscriptions" no longer causes a strict-mode clash.

## Implementation

Landed on 2026-08-10. PR [#46](https://github.com/dadamski/kaleta/pull/46).

| SHA | Author | Date | Message |
|---|---|---|---|
| `8d45711` | Dawid Adamski | 2026-08-10 | fix(transactions): translate type column labels (#46) |

**Files changed:**
- docs/bdd.md
- docs/plans/transactions-type-labels-i18n.md
- src/kaleta/views/components/transaction_table.py
- src/kaleta/views/import_view/preview_section.py
- src/kaleta/views/planned_transactions.py
- src/kaleta/views/reports_canned/largest_transactions.py
- src/kaleta/views/transactions/page.py
- tests/e2e/test_categories.py
- tests/e2e/test_transfer_detection.py
- tests/unit/test_pwa.py
- tests/unit/views/test_transaction_type_labels.py

**Acceptance criteria run** (step 3b):

| Command | Exit |
|---|---|
| `uv run pytest tests/unit -q` | 0 |
| `grep -q "KAL-TXN-006" docs/bdd.md` | 0 |
| `uv run python scripts/spec_coverage.py` | 0 |
| `bash scripts/verify.sh` | 0 |
