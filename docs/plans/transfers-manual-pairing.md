---
plan_id: transfers-manual-pairing
title: Transfer recognition — pair existing rows, suggest pairs, one summary
area: import
effort: medium
status: draft
roadmap_ref: ../roadmap.md#import
---

# Transfer recognition — pair existing rows, suggest pairs, one summary

Gap-closing plan for issue #4 (`KAL-TRF`), from
[`audit-planned-vs-code`](archive/audit-planned-vs-code.md).

## Intent

Import already flags own-account transfers when the counterparty is a
registered account (`KAL-CSV-004`), and
`ImportService.detect_and_link_transfers` links flagged, unlinked legs
(amount ±0.01, configurable window, different accounts). What it cannot
do is repair the common case: two rows imported as an ordinary expense
on one account and an ordinary income on another. Those stay in the
totals and inflate both sides.

## What exists (2026-09-23)

- `Transaction.linked_transaction_id`, `Transaction.is_internal_transfer`
  (`models/transaction.py`).
- `ImportService.detect_and_link_transfers` (`import_service.py`) — only
  looks at rows already flagged `is_internal_transfer`, links them at
  once and reports a count. Button in
  `views/import_view/transfer_section.py`, generic CSV profile only.
  **No test at all.**
- Totals exclude transfers (`ReportService._month_summary`), and the
  ledger colours them neutral (`theme.amount_class`).

## Scope

- **KAL-TRF-001** — `TransactionService.pair_as_transfer(expense_id,
  income_id)`: validates same absolute amount, different accounts,
  opposite directions; sets `type=TRANSFER`, `is_internal_transfer`,
  links both legs. Bulk action "Mark as transfer" in
  `views/transactions/table_actions.py`, enabled when exactly two rows
  are selected.
- **KAL-TRF-002** — `ImportService.suggest_transfer_pairs(...)`
  considers ordinary income/expense rows too, returns pairs instead of
  linking them; the import review shows each pair with accept /
  dismiss. Dismissals persist (same pattern as `DismissedCandidate`).
  The existing auto-link button becomes "accept all".
- **KAL-TRF-003** — a test on `_month_summary` / `current_month_summary`
  (none exists) and a decision on what "the monthly summary" is: the
  dashboard's month widgets, with transfers visible and neutral in the
  ledger. Reword the scenario to name those two places.
- Unit tests for `detect_and_link_transfers` (none today).

Out of scope: cross-currency transfers, transfers to accounts not
registered in Kaleta, auto-categorisation interplay (`KAL-RUL`).

## Acceptance criteria

- `grep -qE "KAL-TRF-001 @automated" docs/bdd.md`
- `grep -qE "KAL-TRF-002 @automated" docs/bdd.md`
- `grep -qE "KAL-TRF-003 @(automated|manual)" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Touchpoints

`services/transaction_service.py`, `services/import_service.py`,
`views/transactions/table_actions.py`, `views/import_view/`,
i18n `en.json` / `pl.json`, `docs/bdd.md`,
`tests/e2e/test_transfer_detection.py`, `tests/unit/services/`.

## Open questions

- Pair window for suggestions: scenario says 2 days, setting defaults to
  3. Default: use the setting; change the scenario literal to the
  setting's default only if the owner prefers.
