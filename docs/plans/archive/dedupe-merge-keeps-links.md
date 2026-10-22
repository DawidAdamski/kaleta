---
plan_id: dedupe-merge-keeps-links
title: Merging duplicate transactions keeps their fund/plan links
area: services (dedupe)
effort: small
status: archived
archived_at: 2026-10-22
roadmap_ref: ../../roadmap.md
---

# Merging duplicate transactions keeps their fund/plan links

## Intent
When the user merges duplicate transactions in Housekeeping,
`DedupeService.merge_transactions` deletes the non-keeper duplicates. A
duplicate may be the row that carries a link the keeper lacks — the
irregular-fund item it settles (`irregular_item_id`) or the planned
occurrence it posts (`planned_transaction_id`). Deleting the duplicate
outright silently loses that link. The keeper must inherit such a link so
a merge never drops a fund payment or a planned-occurrence posting.

## Scope
- Carry a non-keeper's `irregular_item_id` and `planned_transaction_id`
  onto the keeper when the keeper has none of its own, before the
  non-keeper is deleted.
- Never overwrite a link the keeper already holds; the keeper's own link
  wins.
- When several duplicates offer the same link, the lowest-id duplicate
  wins (deterministic tie-break).
- **Not in scope:** any other FK on the transaction (account, category,
  payee, gift, splits, tags), the detection pass, or the UI. Only
  `merge_transactions` changes.

## Acceptance criteria
- `uv run pytest tests/integration/test_dedupe_merge_links.py -q`
- `uv run pytest tests/unit/services/test_dedupe_service.py -q`
- `uv run python scripts/spec_coverage.py`

## Touchpoints
- `src/kaleta/services/dedupe_service.py` — `DedupeService.merge_transactions`
- `tests/integration/test_dedupe_merge_links.py` — new covering test
- `docs/bdd.md` — new scenario KAL-DUP-001 (Housekeeping — Duplicate transactions)

## Implementation notes
- `uq_transactions_planned_occurrence` is `(planned_transaction_id, date)`.
  The SQLAlchemy unit of work flushes UPDATEs before DELETEs, so setting
  the keeper's `planned_transaction_id` to a still-present duplicate's
  value on a shared date would trip the constraint. The fix flushes the
  deletes first, then assigns the carried links to the keeper, mirroring
  the existing flush-before-rename pattern in `merge_payees`.
- Tie-break: duplicates are iterated in ascending `id` order and the first
  non-null link wins; the keeper's own link always takes precedence.

## Implementation
- `c566d24` — fix(dedupe): carry fund/plan links to keeper when merging
  duplicate transactions. `merge_transactions` reassigns `irregular_item_id`
  and `planned_transaction_id` to the keeper (only when the keeper has none),
  flushing deletes before the keeper UPDATE to stay clear of
  `uq_transactions_planned_occurrence`; adds BDD scenarios KAL-DUP-001 /
  KAL-DUP-002 @automated and `tests/integration/test_dedupe_merge_links.py`.
  `gift_id` was deliberately left out (see follow-up chore).
