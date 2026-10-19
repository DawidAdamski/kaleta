---
plan_id: funding-plan-refresh-amount
title: Funding plan — re-planning refreshes the one transfer instead of duplicating
area: services (irregular fund)
effort: small
status: archived
archived_at: 2026-10-19
roadmap_ref: ../../roadmap.md
---

# Funding plan — re-planning refreshes the one transfer instead of duplicating

## Intent
Chore inbox fix (spotted during `gifts-irregular-fund`). `KAL-IRR-003` turns a
fund's monthly contribution into a planned monthly transfer, and
`create_funding_plan` already refuses to plan the same transfer twice. But its
duplicate check keys on the **exact amount**
(`existing.amount == plan.monthly_total`). Once the gifts total folds into
`monthly_total` (slice 2 of Gift Planning), changing the gift list moves the
proposed monthly amount — so the already-planned transfer no longer matches by
amount, the guard misses, and a **second** active transfer is planned beside the
now-stale one. The fund then gets fed twice, from two planned transfers that
differ only in a figure the user never meant to keep.

This slice keys the dedupe on the **route** (source account → fund account),
not the amount, and refreshes the existing transfer's amount in place when the
contribution has changed.

## Scope
`KAL-IRR-006` only: re-accepting the funding plan after the contribution changed
updates the one active transfer rather than adding a second.

- **`IrregularItemService.create_funding_plan`**
  (`src/kaleta/services/irregular_item_service.py`): match the active TRANSFER
  by route — `is_active`, `type is TRANSFER`, `account_id == source.id`,
  `description == "<source> → <target>"` — **ignoring the amount**. Then:
  - no active transfer on the route → create it as today;
  - one exists and its amount already equals `monthly_total` → `ConflictError`
    (nothing changed — the existing "already planned" contract, so the
    `KAL-IRR-003` double-accept test stays true);
  - one exists with a different amount → update that transfer's amount to
    `monthly_total` in place (via `PlannedTransactionService.update`) and
    return it. No second row.
- **BDD**: new `KAL-IRR-006` scenario in `docs/bdd.md` (`@automated`).
- **Tests**: a unit/integration case in
  `tests/integration/test_irregular_fund.py` — plan at 180.00, raise the
  contribution to 240.00, re-accept, assert exactly one transfer reading 240.00.

**Not in scope (binding):**
- No view change. `views/irregular_fund.py` already catches `KaletaError` and
  shows the success toast on a normal return; a refreshed amount returns
  normally, so the existing flow still works. The toast wording ("funding
  created" vs "updated") is left as-is — a separate nicety, not this fix.
- Only the **amount** is refreshed. The transfer keeps its schedule
  (start date, frequency, interval) and name; re-accepting is a figure refresh,
  not a reschedule.
- No change to how `monthly_total` is computed (that is `gifts-irregular-fund`).
- No REST `api/v1` route change.

## Acceptance criteria
- `uv run pytest tests/integration/test_irregular_fund.py -q`
- `grep -q "KAL-IRR-006 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh`

Fail-on-old: before this slice, the dedupe is amount-keyed, so a second accept
after the contribution rose to 240.00 creates a **second** active transfer; the
new test unpacks `[planned] = await ...list()` and fails (two rows) on old code,
and reads a single 240.00 transfer on new code. Expected values are the
scenario literals (180.00 then 240.00).

## Touchpoints
- `src/kaleta/services/irregular_item_service.py`
- `tests/integration/test_irregular_fund.py`
- `docs/bdd.md`

## Open questions
- None blocking. Resolved in decisions below.

## Implementation notes
- **Decision — refresh in place, don't error, when the amount changed.** The
  chore offered two fixes (key the dedupe on the route, or update the existing
  plan in place); this does both. Keying on the route is what makes "the same
  transfer" stable across a changing contribution; updating the matched row in
  place is the friendly outcome — the user re-accepts the suggestion and the one
  transfer now reads the new figure, with no duplicate to clean up.
- **Decision — equal amount still conflicts.** When the route already has a
  transfer at the exact `monthly_total`, nothing changed, so `ConflictError`
  ("already planned") stands. This preserves the `KAL-IRR-003` double-accept
  contract and its test, and keeps the "I clicked twice by mistake" case honest.
- **Known limitation — the route match is by `description`** (`"<source> →
  <target>"`), the same string the pre-existing dedupe used. If a user renames
  the planned transfer by hand, the next accept no longer recognises it as the
  same route and plans a fresh one. Out of scope here (it would need a stored
  fund/route reference on the planned transfer rather than a name match); noted
  so it is not mistaken for part of this fix.
</content>
</invoke>

## Implementation

Landed on 2026-10-19 (PR #289).

| SHA | Author | Date | Message |
|---|---|---|---|
| `697858c` | Dawid Adamski | 2026-10-19 | Merge pull request #289 from DawidAdamski/fix/funding-plan-refresh-amount |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/funding-plan-refresh-amount.md
- src/kaleta/services/irregular_item_service.py
- tests/integration/test_irregular_fund.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
