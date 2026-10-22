---
plan_id: dashboard-recent-transfer-sign
title: Recent-transactions card signs a transfer leg by its direction
area: dashboard
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Recent-transactions card signs a transfer leg by its direction

## Intent
The dashboard's recent-transactions widget signed every amount from the
transaction *type* alone, so a transfer's incoming leg read negative — the
opposite of what the ledger now shows after PR #330
(`ledger-transfer-leg-sign`, KAL-TRF-005). The dashboard and the ledger read
the same money and must not disagree about which way it moved.

## Scope
Covers:
- Extend the view-layer wrappers in
  `src/kaleta/views/components/amount_label.py`
  (`format_signed_amount`, `signed_amount_class`) with an optional
  `transfer_direction: TransferDirection | None = None`, defaulting to the
  current behaviour for callers that pass none (income, expense, planned
  occurrences).
- Thread `tx.transfer_direction` through the three signing sites in
  `src/kaleta/views/dashboard_widgets/recent_transactions.py` (the phone
  label + its tone, and the table's `amount` + `amount_value`), exactly as
  `TransactionService.build_table_row` already does for the ledger.

Does NOT cover (binding):
- The sign/colour convention itself (lives in `TransactionService`; unchanged).
- Any other widget or view. The planned-occurrence callers
  (`upcoming_planned`, `forecast`, `planned_dialog`) keep the two-arg call —
  those rows have no `transfer_direction`.
- Colour: a transfer leg stays **neutral** whichever way it went (KAL-TXN-006,
  and the ledger table paints it the same). Direction changes only the *sign*.

## Acceptance criteria
- `uv run pytest tests/unit/views/test_amount_label.py -q`
- `uv run pytest tests/integration/test_transfer_pairing.py -q`
- `uv run python scripts/spec_coverage.py`
- `uv run ruff check .`
- `uv run mypy src/`
- `uv run lint-imports`

## Touchpoints
- `src/kaleta/views/components/amount_label.py`
- `src/kaleta/views/dashboard_widgets/recent_transactions.py`
- `tests/unit/views/test_amount_label.py`
- `tests/integration/test_transfer_pairing.py`
- `tests/e2e/test_dashboard_transfer_sign.py`
- `docs/bdd.md` (new scenario KAL-DSH-011)

## Open questions
None.

## Implementation notes
- `recent_transactions` rows come from `ReportService.recent_transactions(10)`
  — real `Transaction` ORM objects, so `transfer_direction` is available
  (unlike planned/forecast occurrences, which have no direction and keep the
  two-arg call).
- The widget only shows **non-internal** transfers: the query filters
  `is_internal_transfer == False`, and `pair_as_transfer` marks a recognised
  own-account pair internal. So the legs that reach the card are non-internal
  transfer rows (e.g. a manual transfer or a transfer to an external party),
  which is exactly what the tests seed.
- `signed_amount_class` accepts `transfer_direction` for a signature that
  matches `format_signed_amount`, but does not use it: colour follows the raw
  type (`amount_class`), and `amount_class("transfer")` is already neutral —
  matching the ledger table's Vue slot. Only the figure's sign changes.
- Cover: KAL-DSH-011 is carried by `tests/e2e/test_dashboard_transfer_sign.py`
  (the rendered-widget cover) and `tests/integration/test_transfer_pairing.py`
  (`test_recent_transactions_card_signs_transfer_legs_by_direction`, which
  drives `recent_transactions` + the widget's format helpers). Both live where
  `spec_coverage.py` scans (integration + e2e). The e2e seeds two **unlinked**
  legs so each row deletes cleanly in teardown — a mutual
  `linked_transaction_id` self-FK would block the raw delete.
- BDD literals used in the verification tests: `-500.00` (leaving) and
  `+500.00` (arriving), taken straight from KAL-DSH-011.

## Implementation (filled by plan-archiver)
