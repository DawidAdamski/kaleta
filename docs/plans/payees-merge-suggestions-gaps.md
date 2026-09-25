---
plan_id: payees-merge-suggestions-gaps
title: Payee identities — suggestions on the Payees page, token matching, merge under a new name
area: payees
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-automatic-deduplication-suggestions
---

# Payee identities — suggestions on the Payees page, token matching, merge under a new name

Gap-closing plan for issue #1 (`KAL-PID-001`, `KAL-PID-002`), from
[`audit-planned-vs-code`](archive/audit-planned-vs-code.md). `KAL-PID-003` is
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

## Implementation notes

- **Open question — fold into `payees-identities-automerge`?** Took the
  default: no. The matcher (`_core_tokens` + pass 2 of
  `DedupeService.similar_payees`) is what that plan can build on.
- **Matcher.** `similar_payees` now runs three passes: normalised equality
  (unchanged), then *core name* — legal-form runs ("sp. z o.o.", "S.A.",
  "GmbH"…), any token containing a digit, and location tokens (country and
  the largest Polish cities, both spellings) stripped — grouping equal cores
  or a core that is a **whole-token** prefix of another ("netflix" takes
  "netflix international"), then Levenshtein on what is left (unchanged, still
  governed by the user's max-distance setting). Guards against noise: cores
  under 3 characters are never grouped; prefix absorption needs a core of at
  least 4 characters ("abc" does not take "abc hurtownia budowlana").
  Housekeeping gets the better matcher too — same service.
- **New name on merge.** Both merge paths take an optional `new_name`:
  `DedupeService.merge_payees` (suggestions, on /payees and /housekeeping) and
  `PayeeService.merge` (the manual multi-select merge dialog and
  `POST /api/v1/payees/merge`, new optional `new_name` field). The rule lives
  once, in `PayeeService.check_merge_name`, and runs before any write: blank
  keeps the keeper's name; the name may reuse a *merged* payee's name (it is
  deleted and flushed before the rename, since the unit of work would
  otherwise run the UPDATE before the DELETE and trip `UNIQUE(name)`); a name
  held by a payee **outside** the merge raises `ConflictError` (API 409); over
  200 characters raises `ValidationError`.
- **Why the two merge paths stay separate.** `PayeeService.merge` does not
  reassign `Subscription.payee_id` while `DedupeService.merge_payees` does.
  Unifying them changes the manual merge's semantics (and its return count for
  unknown ids), which is outside this plan — logged in `docs/plans/chores.md`.
- **UI.** The housekeeping payee group became a shared component,
  `views/components/payee_merge.py` (`PayeeMergeSuggestion` +
  `MergeConfirmDialog`), with a "New name (optional)" input. /payees renders a
  "Merge suggestions" card above the table only when there are groups; it
  refreshes after add/edit/delete/merge. The manual merge dialog got the same
  optional new-name field. Merge failures (e.g. the conflict) now surface as a
  toast via `handle_kaleta_error` on both pages instead of an unhandled error.
- **E2e isolation.** The e2e DB is shared across a session and the prefix rule
  would have pulled KAL-PID-003's "Lidl PID E2E" payee into the Lidl group, so
  merging it would break PID-003 if it ran later. That test's payee is renamed
  to "Kaufland PID E2E" (test-only change; the scenario names no merchant).
  The new tests use `get_or_seed_payee`, so they pass in either order.
  Rule 4: the green-washing check flags "assertions removed" in
  `tests/e2e/test_payee_identities.py` — those lines are the same PID-003
  assertions with the literal and variable renamed (`lidl_*` → `kaufland_*`,
  one long `assert` wrapped by the formatter); none was dropped or loosened.
