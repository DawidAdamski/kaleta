---
plan_id: payees-merge-suggestions-gaps
title: Payee identities — suggestions on the Payees page, token matching, merge under a new name
area: payees
effort: small
status: draft
roadmap_ref: ../roadmap.md#cross-cutting-automatic-deduplication-suggestions
---

# Payee identities — suggestions on the Payees page, token matching, merge under a new name

Gap-closing plan for issue #1 (`KAL-PID-001`, `KAL-PID-002`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md). `KAL-PID-003` is
`@automated`. The larger identities/auto-merge work stays in
[`payees-identities-automerge`](payees-identities-automerge.md).

## What exists (2026-09-23)

- `DedupeService.similar_payees` (normalised equality or Levenshtein
  ≤ 3) and `merge_payees`; suggestions render on **/housekeeping**, not
  on the Payees page. Manual merge on the Payees page and
  `POST /api/v1/payees/merge`.
- The scenario's own pair, "LIDL SP. Z O.O." / "Lidl 1234 Warszawa", is
  **not** detected: normalised lengths differ by 5, over the threshold.
- Both merge flows keep one existing name; neither accepts a new one
  ("Lidl").

## Scope

- **PID-001** — token/prefix matching (legal suffixes such as
  "sp. z o.o.", store numbers, city names stripped) in
  `similar_payees`; a suggestions strip on the Payees page reusing the
  housekeeping component.
- **PID-002** — merge accepts an optional new name for the keeper.
- E2e for both (none of the merge UIs has one today).

## Acceptance criteria

- `grep -qE "KAL-PID-001 @automated" docs/bdd.md`
- `grep -qE "KAL-PID-002 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Fold into `payees-identities-automerge`? Default: no — this is the
  small, shippable half; that plan can build on the matcher.
