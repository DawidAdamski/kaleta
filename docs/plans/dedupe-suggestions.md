---
plan_id: dedupe-suggestions
title: Cross-cutting — duplicate suggestions surface
area: cross-cutting
effort: medium
status: draft
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
