---
plan_id: transfers-manual-pairing
title: Transfer recognition — pair existing rows, suggest pairs, one summary
area: import
effort: medium
status: archived
archived_at: 2026-09-30
roadmap_ref: ../../roadmap.md#import
---

# Transfer recognition — pair existing rows, suggest pairs, one summary

Gap-closing plan for issue #4 (`KAL-TRF`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md).

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

## Implementation notes

- **Open question (pair window).** Took the default: suggestions use the
  `transfer_pairing_days` setting (default 3). The scenario's "within 2 days"
  stays as written — 2 is inside the default window, and the tests use it.
- **KAL-TRF-001.** `TransactionService.pair_as_transfer(expense_id, income_id,
  *, amount_tolerance=0)` validates: two distinct rows, different accounts,
  same currency (cross-currency is out of scope), equal absolute amount
  (within tolerance), neither already linked, neither split, and direction
  (an income cannot be the outgoing leg, an expense cannot be the incoming
  one; a row already typed `transfer` may stand on either side, which is
  what an mBank import that recognised one side produces). Both legs become
  `type=TRANSFER`, `is_internal_transfer=True`, `category_id=None`, linked to
  each other. Payee, tags, notes, dates and descriptions are kept.
  The ledger doesn't know which selected row is which leg, so the bar
  calls `pair_selected_as_transfer(a, b)`, which orients them by type via
  `TransactionService.orient_transfer_legs` (shared with the suggester).
  Button is always on the selection bar, disabled unless exactly two rows
  are ticked (`data-mark-transfer`).
- **KAL-TRF-002.** `ImportService.suggest_transfer_pairs(max_days_apart,
  amount_tolerance, date_from, date_to)` considers every unlinked, non-split
  row — ordinary income/expense as well as flagged transfer legs — and
  returns `TransferPairSuggestion`s without writing anything. Two expenses
  or two incomes never pair. Each row appears in at most one pair; closest
  date wins, then closest amount, then lowest ids. Sorting by amount keeps
  the scan to the rows within tolerance instead of all pairs.
  Dismissals persist in a new table `dismissed_transfer_pairs`
  (`DismissedTransferPair`, migration `3b168fa7bb71`), keyed by the two row
  ids stored lowest-first, so a dismissal holds whichever way round the
  pair was offered. `DismissedCandidate` itself was not reused: it is keyed
  by payee/merchant pattern and amount bucket, and a pair is a fact about
  two rows. Rows cascade-delete their dismissals (FK `ON DELETE CASCADE`;
  SQLite enforces it because `db/session.py` turns on `PRAGMA foreign_keys`.
  The in-memory unit-test engine does not, so no unit test asserts the cascade).
- **Where the review lives.** The transfer card moved from the Preview step
  (where it was shown only for the generic profile, before the rows existed)
  to the Confirm step, for every profile, shown once a run has finished.
  Suggestions are scoped to the span of dates of the rows this run
  imported, widened by the pairing window, so years of unrelated history
  are not offered at once.
- **Accept all.** `detect_and_link_transfers` keeps its name and return
  value (pairs linked) but is now "accept every current suggestion" —
  same pairs, dismissals respected, same date bounds. Behaviour change:
  it now also converts matching ordinary income/expense pairs, and it
  refuses pairs across currencies (the old code didn't check). It had
  no tests; `tests/unit/services/test_transfer_pairing.py` covers it.
- **KAL-TRF-003.** Decision: "the monthly summary" is the dashboard's month
  widgets (`month_income`, `month_expenses`, `month_net`, all reading
  `ReportService.current_month_summary` → `_month_summary`), plus the
  ledger's neutral colouring (`theme.amount_class("transfer")`). Scenario
  reworded to name both. No production change was needed: `_month_summary`
  already excludes `is_internal_transfer`; the new integration test pins it.
- **Tests.** `tests/integration/test_transfer_pairing.py` covers
  TRF-001/002/003 at the service level; `tests/e2e/test_transfer_detection.py`
  covers TRF-001 (ledger bar) and TRF-002 (import Confirm step, new fixture
  `mbank_transfer_pairs.csv` dated 2019-03 with odd amounts, to keep clear of
  other tests' rows in the shared e2e DB).
- **Review follow-ups.** The review window moved into
  `ImportService.transfer_review_window` (unit-tested) instead of living in
  the view. The "Mark as transfer" tooltip now says both rows lose their
  category, since pairing clears it and there is no undo. Accept-all commits
  pair by pair: a failure part-way leaves the earlier pairs linked, and the
  view refreshes the list, which the docstring now says.
- **Found, not fixed** (chore inbox): Money Flow infers transfer direction
  from row ids, which pairing does not guarantee.

## Implementation

Landed on 2026-09-30 (PR #169).

| SHA | Author | Date | Message |
|---|---|---|---|
| `c413e43` | Dawid Adamski | 2026-09-30 | Merge pull request #169 from DawidAdamski/plan/transfers-manual-pairing |

**Files changed:**
- alembic/versions/3b168fa7bb71_add_dismissed_transfer_pairs.py
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/transfers-manual-pairing.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/models/__init__.py
- src/kaleta/models/dismissed_transfer_pair.py
- src/kaleta/services/import_service.py
- src/kaleta/services/transaction_service.py
- src/kaleta/views/import_view/page.py
- src/kaleta/views/import_view/transfer_section.py
- src/kaleta/views/transactions/page.py
- src/kaleta/views/transactions/table_actions.py
- tests/backup_helpers.py
- tests/e2e/fixtures/mbank_transfer_pairs.csv
- tests/e2e/test_transfer_detection.py
- tests/integration/test_transfer_pairing.py
- tests/unit/services/test_transfer_pairing.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
