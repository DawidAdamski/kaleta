---
plan_id: transactions-split-discoverability
title: Transactions — make splits discoverable (row indicator, row action, dialog hint)
area: transactions
effort: small
status: archived
archived_at: 2026-08-11
roadmap_ref: ../roadmap.md#transactions
---

# Transactions — make splits discoverable

## Intent

Dogfooding: the user asked for the ability to split a shop receipt
across categories (Lidl: food + cleaning supplies) — **a feature that
already exists** (ADR-012, KAL-SPL-001…004 `@automated`, split editor
in both add and edit dialogs) — and did not find it. Two problems:

1. The entry point is a small "Podziel" switch inside the add/edit
   dialog (`add_dialog.py:93`), easy to miss among ~8 fields.
2. A split transaction is indistinguishable from a normal row in the
   transactions table — no icon, no way to see the split lines without
   opening the edit dialog (`transaction_table.py` contains no split
   rendering at all).

This is the second discoverability miss in dogfooding (after wizard →
personal loans); features must advertise themselves where the user
already looks.

## Scope

- **Split indicator in the table**: rows whose transaction has split
  lines get a small icon (e.g. `call_split`) next to the category
  cell, with a tooltip listing the lines ("180,00 Spożywcze · 34,50
  Chemia"). Requires the row dict to carry `has_splits` (+ prefetched
  lines for the tooltip) — extend the row-build query without N+1
  (selectinload of splits already exists for the edit path; reuse).
- **Category cell for splits**: show "Podzielona (N)" (i18n) instead
  of a single category name — today it presumably shows the main
  category, which misrepresents the data.
- **Row action**: in the actions column (`table_actions.py`), add a
  "Podziel" action that opens the edit dialog with the split switch
  already ON and one empty split row focused — one click from "I want
  to split this" to doing it.
- **Dialog affordance**: promote the switch visually — move it next
  to the category select with the existing
  `transactions.split_tooltip` shown as a caption, not only a hover
  tooltip.
- **BDD**: extend Feature: Transaction Splits with the next free
  KAL-SPL IDs (`grep -o "KAL-SPL-[0-9]*" docs/bdd.md | sort -u` before
  assigning): split row shows indicator + line summary; "split" row
  action opens the editor pre-armed. Ship the e2e below in the same
  PR and tag these scenarios `@automated` from the start.

Out of scope: split-aware filtering/reports (splits already flow into
budgets/reports via `transaction_splits`), editing split lines inline
in the table, receipt OCR.

## Tests (same PR as the implementation)

Unit (`tests/unit/`):

1. Row-build helper: a transaction with 2 split lines produces
   `has_splits=True`, `split_count=2`, and the category display value
   "Podzielona (2)" / "Split (2)"; a plain transaction produces
   `has_splits=False` and its category name. If the helper lives in a
   view module, extract it to a pure function so it is unit-testable
   (views hold no logic — architecture contract).
2. List query: fetching the transactions page with a split transaction
   present does not lazy-load per row (assert eager-loaded splits are
   available on the returned objects — guards the N+1).

E2E (`tests/e2e/test_transactions.py`, docstrings with
`Covers: KAL-SPL-<new ids>`):

3. Create a split transaction (reuse the KAL-SPL-001 flow), return to
   the table: the row shows the split icon and "Split (2)" in the
   category column; a non-split row shows neither.
4. Click the row's "Split" action on a plain transaction: the edit
   dialog opens with the split switch ON and the split editor visible;
   add two balanced lines, save; the table now shows the indicator.
5. Regression: existing split e2e (KAL-SPL-001/004) stays green —
   selectors must not depend on the old single-category cell text.

## Acceptance criteria

- `uv run pytest tests/unit -q`
- `uv run pytest tests/e2e/test_transactions.py -q`
- `grep -qE "KAL-SPL-00[5-9]" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` Hover tooltip lists the split lines ("180,00 Spożywcze ·
  34,50 Chemia"); amount colours unchanged; dialog switch placement
  reads clearly in both light and dark mode.

## Touchpoints

- `src/kaleta/views/components/transaction_table.py` (columns, slots)
- `src/kaleta/views/transactions/page.py` (row build), `table_actions.py`,
  `add_dialog.py` / `edit_dialog.py` (switch placement)
- `src/kaleta/services/transaction_service.py` (row query — only if
  splits are not already eager-loaded on the list path)
- `src/kaleta/i18n/locales/en.json` + `pl.json`
- `docs/bdd.md`, `tests/e2e/test_transactions.py`

## Open questions

1. Tooltip vs expandable row for the lines? Default: **tooltip** —
   zero layout churn; an expandable row is a follow-up if tooltips
   prove clunky on mobile/PWA.

## Implementation notes

- Next free IDs were KAL-SPL-005 / KAL-SPL-006 (001–004 already automated).
- Row fields (`has_splits`, `split_count`, `split_tooltip`) live on
  `TransactionService.build_table_row`; category label i18n is applied in
  `attach_split_labels` (same pattern as `attach_type_labels`) so the service
  stays free of `t()`.
- CSV export keeps the detailed `category_display_label` (`(Split: A, B)`);
  only the table uses `Split (N)` / `Podzielona (N)`.
- Per-row "Split" action is in the table actions cell (not the bulk bar in
  `table_actions.py`); emits `split_tx` and opens edit with `arm_split=True`.
- Edit dialog previously had no split switch — added alongside the add-dialog
  affordance (switch + caption next to category).

## Implementation

Landed on 2026-08-11. PR [#50](https://github.com/dadamski/kaleta/pull/50).

| SHA | Author | Date | Message |
|---|---|---|---|
| `4721d5c` | Dawid Adamski | 2026-08-11 | feat(transactions): make splits discoverable in the table and dialogs (#50) |

**Files changed:**
- docs/bdd.md
- docs/plans/transactions-split-discoverability.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/services/transaction_service.py
- src/kaleta/views/components/transaction_table.py
- src/kaleta/views/transactions/add_dialog.py
- src/kaleta/views/transactions/edit_dialog.py
- src/kaleta/views/transactions/page.py
- tests/e2e/test_transactions.py
- tests/unit/services/test_transaction_service.py
- tests/unit/views/test_transaction_split_labels.py

**Acceptance criteria run** (step 3b):

| Command | Exit |
|---|---|
| `uv run pytest tests/unit -q` | 0 |
| `uv run pytest tests/e2e/test_transactions.py -q` | infra (see note) |
| `grep -qE "KAL-SPL-00[5-9]" docs/bdd.md` | 0 |
| `uv run python scripts/spec_coverage.py` | 0 |
| `bash scripts/verify.sh` | 0 |

**Notes:** The e2e test run (`tests/e2e/test_transactions.py`) requires a dedicated
test server on port 8081 which could not be spawned in the archival environment.
The tests are confirmed passing: terminal 1 shows `./scripts/verify.sh --e2e`
completed with "VERIFY OK (incl. e2e)" during the PR.
