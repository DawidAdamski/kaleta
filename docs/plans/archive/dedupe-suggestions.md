---
plan_id: dedupe-suggestions
title: Cross-cutting — duplicate suggestions surface
area: cross-cutting
effort: medium
status: archived
archived_at: 2026-04-23
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Cross-cutting — duplicate suggestions surface

## Intent

After imports and bulk edits, the DB accumulates near-duplicate
entries (same transaction from two statements; two spellings of the
same payee; two categories with the same meaning). Surface candidates
to the user and let them merge with one click.

## Scope

Three detectors, shown under a new **Housekeeping** entry point
(accessible from Settings and from a Dashboard widget):

- **Duplicate transactions** — same account, same amount, same date
  within ±1 day, similar description. User picks keeper → the other
  is deleted.
- **Similar payees** — normalised names collide (case, diacritics,
  punctuation stripped) or high Levenshtein similarity. Merge into
  one; all transactions reassigned.
- **Redundant categories** — empty or near-empty categories whose
  name or path suggests another existing one. Merge reassigns
  transactions and budgets.

Out of scope:
- Auto-merge without confirmation.
- ML-based semantic matching — string heuristics only for v1.

## Acceptance criteria

- Housekeeping page lists the three detector groups with counts.
- Each suggestion card shows the candidates side-by-side with amounts
  / counts.
- Merge action is atomic (all-or-nothing) and reversible via
  audit-log entry (see Dismissals / undo plan — out of scope here).
- Dismissed suggestions stay dismissed (per-user flag) until the
  underlying data changes enough to re-qualify.

## Touchpoints

- `src/kaleta/services/dedupe_service.py` — new service, one method
  per detector.
- `src/kaleta/views/housekeeping.py` — new view.
- `src/kaleta/services/transaction_service.py`,
  `payee_service.py`, `category_service.py` — merge methods.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Levenshtein threshold for payee similarity — start at 2 for names
  ≤10 chars, 3 for longer; measure false-positive rate during
  dogfood.
- Undo window — add an audit log later; for v1 rely on DB backups.

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-23.

| SHA | Author | Date | Message |
|---|---|---|---|
| `f2abc5e` | Dawid | 2026-04-23 | feat(housekeeping): duplicate / payee / category suggestions |

**Files changed:**
- `src/kaleta/services/dedupe_service.py` (new — 3 detectors + 3 merge methods + Levenshtein/normalise helpers)
- `src/kaleta/services/__init__.py` (export DedupeService)
- `src/kaleta/views/housekeeping.py` (new — /housekeeping page with 3 sections, per-group keeper picker, confirm-before-merge dialog)
- `src/kaleta/views/layout.py` (nav entry under Tools → /housekeeping)
- `src/kaleta/main.py` (registers housekeeping.register())
- `src/kaleta/i18n/locales/en.json` (nav.housekeeping + full housekeeping.* block)
- `src/kaleta/i18n/locales/pl.json` (nav.housekeeping + full housekeeping.* block)
- `tests/unit/services/test_dedupe_service.py` (15 tests: normaliser, Levenshtein, description-alike, 3 detectors, 3 merges including budget-conflict path)

**What shipped:**
- `DedupeService.duplicate_transactions()` — scans the trailing 365 days of non-transfer tx, buckets by (account_id, amount), clusters within ±1 day sharing a 4+ char description token. Returns groups for the UI.
- `DedupeService.similar_payees()` — pass 1: group by normalised name (lowercase, NFKD, strip diacritics+punct). Pass 2: Levenshtein pairs on the remainder with ≤2 threshold for names ≤10 chars, ≤3 for longer. Pre-normalises once, fast-rejects when length difference exceeds threshold or short side < 3 chars.
- `DedupeService.redundant_categories()` — groups by (normalised name, CategoryType) so income/expense never cross-merge.
- Three merge methods: `merge_transactions(keeper_id, other_ids)` deletes non-keepers; `merge_payees(keeper_id, other_ids)` reassigns Transaction.payee_id + Subscription.payee_id then deletes victims; `merge_categories(keeper_id, other_ids)` reassigns Transactions, TransactionSplits, PlannedTransactions, ReserveFund.backing_category_id, Subscription.category_id, and Category.parent_id, drops victim budgets whose periods conflict with the keeper's, reassigns non-conflicting victim budgets.
- `/housekeeping` view (new route, nav entry under Tools): 3 stacked section cards with count badges, per-group candidate cards with side-by-side labels/amounts/tx-counts, keeper picker defaults to highest tx-count, shared confirm-before-merge dialog.
- i18n complete in EN + PL (section heads, hints, empty states, confirm copy, result toasts).
- Performance: page renders in ~1.5 s on the live dev DB after the Levenshtein pre-filter; 123 duplicate-transaction candidate groups surfaced on the real DB.

**Partial coverage / deferred:**
- **Dismissal persistence** — plan called for per-user flag so dismissed suggestions stay dismissed until underlying data changes. Not shipped in v1; would mirror the existing `DismissedCandidate` pattern from subscriptions.
- **Audit-log backed undo** — merges commit atomically but are not reversible in v1.
- **Dashboard widget** — plan mentions "accessible from Settings and from a Dashboard widget"; only the Tools-nav entry shipped.
- **Detector tuning knobs** — thresholds are module-level constants (`PAYEE_LEVENSHTEIN_SHORT_THRESHOLD` etc.); no Settings UI to tune them.
- **Cross-account duplicate-tx detection** — v1 buckets by `account_id`; a transaction imported into two different accounts is not flagged.
- **Payee-merge across future FK tables** — only Transaction + Subscription FKs are reassigned today; any future payee-related FK tables must be wired separately.
