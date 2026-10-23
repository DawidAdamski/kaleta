---
plan_id: dedupe-merge-keeps-gift-id
title: Duplicate-merge carries gift_id to the keeper
area: housekeeping (dedupe)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Duplicate-merge carries gift_id to the keeper

## Intent
When a user merges duplicate transactions, the keeper must inherit a link
that only a deleted duplicate carried. `DedupeService.merge_transactions`
already carries `irregular_item_id` and `planned_transaction_id`, but not
`gift_id` — the gift a transaction settles (`Transaction.gift_id`, FK
`gifts.id` ON DELETE SET NULL). Deleting a duplicate that carries `gift_id`
silently loses the link between the gift and the expense that paid for it.

## Scope
Covers, and only:

- `src/kaleta/services/dedupe_service.py`, `merge_transactions`: mirror the
  existing `carried_irregular_item_id` / `carried_planned_transaction_id`
  pattern for `gift_id` — a `carried_gift_id`, an `if keeper.gift_id is None:`
  block picking the lowest-id duplicate's `gift_id`, inclusion in the
  "has anything to carry" guard, and `keeper.gift_id = carried_gift_id`.
- Docstring update to mention the gift link.
- New BDD scenario `KAL-DUP-003` (`@automated`) in `docs/bdd.md`.
- New integration test covering the carry, in
  `tests/integration/test_dedupe_merge_links.py`.

Not in scope: any other FK carry, the `merge_payees` / `merge_categories`
flows, or the duplicate-detection logic.

## Acceptance criteria

- `uv run pytest tests/integration/test_dedupe_merge_links.py -n 2 -m "not slow"`
- `grep -c "KAL-DUP-003" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- `uv run mypy src/`
- `uv run lint-imports`

## Touchpoints
- `src/kaleta/services/dedupe_service.py`
- `docs/bdd.md`
- `tests/integration/test_dedupe_merge_links.py`
- `docs/plans/chores.md` (tick the line)

## Open questions
None.

## Implementation notes
Closes the gap flagged by the Wave-10 dedupe lane: the earlier
`dedupe-merge-keeps-links` fix (`c566d24`, KAL-DUP-001/002) carried only
`irregular_item_id` and `planned_transaction_id` because the chore named
only those two; `gift_id` is structurally the same kind of link and is now
carried identically — keeper wins, else the lowest-id duplicate, and the
deletes flush before the keeper UPDATE (shared with the existing carry).
