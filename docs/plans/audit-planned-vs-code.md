---
plan_id: audit-planned-vs-code
title: Audit — @planned BDD features vs existing code (2026-07-07)
area: cross-cutting
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Audit — `@planned` BDD features vs existing code

**Finding: 10 of 16 `@planned` features already exist in some form.**
The BDD spec (written from the product vision) and the Backlog issues
treat them as greenfield. Like Transaction Splits turned out to be,
most are "half-wired": service + model exist, but specific workflow
behaviours from the scenarios are unverified or missing. Each feature
below needs either a **verification pass** (retag scenarios, close
issue) or a **gap-closing plan** (the splits pattern).

## Feature-by-feature

| Feature | Evidence in code | Status | Action |
|---|---|---|---|
| KAL-PID Payee Identities | `dedupe_service.similar_payees()`, `merge_payees()`; merge e2e (KAL-PAY-007/008) | **Mostly done** | Verify PID-001/002 in UI → retag; PID-003 (top payees) likely the only gap |
| KAL-SUB Subscriptions | Full `subscription_service` (cadence, cancel, reactivate, mute, `category_group_monthly_total`), `views/subscriptions/`, `detect_candidates()` | **Mostly done** | Verify SUB-001…004 → retag; check normalised monthly total maths |
| KAL-DBT Debt Tracking | `personal_loan_service` (counterparties, loans by status), `views/personal_loans/` | **Mostly done** | Verify DBT-001…004; check repayment↔transaction linkage and "not an expense" in stats |
| KAL-FND Reserve Funds | `ReserveFundKind.EMERGENCY`, `months_of_coverage`, survival-months footer in `safety_funds.py` | **Mostly done** | Verify FND-001/002 → retag; FND-003 (dashboard warning below target) to confirm |
| KAL-API Public API | `/api/v1/` accounts, budgets, categories, institutions, payees, transactions; Swagger UI in `main.py` | **Mostly done** | Verify API-001…003 → retag (API integration tests already exist) |
| KAL-TRF Transfer Recognition | Import detects own-account transfers (CSV-004 @automated); `import_service` pairs unlinked TRANSFER legs (amount ±0.01, ≤3 days, different accounts); `is_internal_transfer` excluded from totals everywhere | **Partial** | Gap: TRF-001 manual "mark two rows as transfer" for rows imported as expense+income; TRF-002 suggestions for those rows. Gap-closing plan |
| KAL-GOL Savings Goals | `ReserveFundKind.VACATION`, `target_amount`, goal progress in `safety_funds.py` | **Partial** | Skarbonki = vacation reserve funds. Verify GOL-001/002; gaps likely: pace hint (GOL-003), close-and-release (GOL-004). Align scenario wording with reserve-fund model |
| KAL-IRR Irregular Fund | `ReserveFundKind.IRREGULAR` exists in model + views | **Partial** | Fund container exists; missing: itemised yearly items, ÷10 monthly contribution, pay-item-from-fund linkage. Gap-closing plan |
| KAL-REC Recurring Detection | `subscription_service.detect_candidates()` + `DismissedCandidate` model | **Partial** | Detection exists for subscriptions; REC-002/003 (convert to planned transaction, link history) and price-drift flag to check/build |
| KAL-QIK Quick Entry | `Alt+N` opens add dialog, `Enter` saves, PageUp/Down paging, `?` help dialog | **Partial** | QIK-001 near-done; gaps: QIK-002 (remember context), QIK-003 (save-and-add-next) |
| KAL-CMP Planning Comparisons | `yearly_plan_service.diff()`, year-vs-year (KAL-BUD-010), readiness stage 3 copies budgets | **Partial** | Building blocks exist; side-by-side prev-month/prev-years view while planning to build |
| KAL-ANR Annual Review | `yearly_plan_service` (payload, diff, apply), `views/budget_plan/`, wizard | **Partial** | Year-plan tooling exists; guided review flow (summary → carry-forward → commitments) to build on top |
| KAL-RUL Auto-categorisation | nothing (only per-file import mapping memory) | **Greenfield** | Stays in v0.3.0 as planned |
| KAL-GFT Gift Planning | nothing | **Greenfield** | Stays in Backlog |
| KAL-AIN AI Insights | nothing (by design — paid tier) | **Greenfield** | Stays in Backlog |
| KAL-INV Investments | `asset_service` CRUD, `net_worth_service` with asset/liability split | **Partial** | Verify INV-001…003 against Asset model fields (unit price? valuation updates?); INV-004 (link contribution) likely missing |

## Recommended sequence

1. **Verification wave (cheap, high signal):** one session walking
   PID, SUB, DBT, FND, API, GOL scenarios against the running app;
   retag what holds (`@manual`/`@automated`), file concrete gaps as
   checkboxes on the feature's issue. Expect several issues to shrink
   dramatically or close.
2. **Re-milestone after verification:** mostly-done features are
   quick wins — pull their remaining gaps from Backlog into
   v0.2.0/v0.3.0; the Backlog then reflects real effort.
3. **Gap-closing plans (splits pattern):** TRF first (top user pain,
   v0.3.0), then IRR + REC.
4. **Spec hygiene going forward:** before writing new `@planned`
   scenarios, grep models/services for prior art — this audit exists
   because the spec was written from vision without checking the code.

## Acceptance criteria

- [manual] Every feature above has either retagged scenarios or a
  gap-closing entry (issue checkbox or plan) — no `@planned` feature
  left misrepresenting existing code.
- `grep -qE "KAL-FND-003 @automated" docs/bdd.md`
- `grep -qE "KAL-REC-001 @automated" docs/bdd.md`
- `grep -qE "KAL-CMP-003 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `test -f docs/plans/transfers-manual-pairing.md`
- `test -f docs/plans/payees-merge-suggestions-gaps.md`
- `test -f docs/plans/subscriptions-panel-gaps.md`
- `test -f docs/plans/transactions-quick-entry-flow.md`
- `test -f docs/plans/funds-reserve-derived-target.md`
- `test -f docs/plans/debts-ledger-link.md`
- `test -f docs/plans/recurring-to-planned.md`
- `test -f docs/plans/budgets-plan-comparisons-gaps.md`
- `test -f docs/plans/funds-savings-goals.md`
- `test -f docs/plans/funds-irregular-items.md`
- `test -f docs/plans/budgets-annual-review.md`
- `uv run pytest tests/e2e/test_reserve_funds.py tests/e2e/test_subscriptions.py tests/e2e/test_budget_comparisons.py -q`

## Implementation notes

**Verification 2026-08-26 (status refresh, not a full retag pass):**

| Feature | Now | Notes |
|---|---|---|
| KAL-API | **DONE** | 001–004 `@automated` |
| KAL-RUL | **DONE** | 001–004 `@automated`; plan archived |
| KAL-SUB / FND / DBT / PID | **PARTIAL** | mix of `@automated` and `@planned` |
| KAL-TRF / GOL / IRR / REC / QIK / CMP / ANR / INV / GFT / AIN | **OPEN** | still largely `@planned`; gap plans sparse (REC partially in `wizard-unplanned-radar`) |

Acceptance criterion still unmet — keep `draft` until verification wave
or gap-closing plans close the remaining `@planned` features.

**Verification wave 2026-09-23 (`plan/audit-planned-vs-code`) — closes
the criterion.** Every remaining `@planned` scenario of the 16 features
was read step by step against models, services, views and tests. Strict
rule: a scenario is implemented only if *every* Given/When/Then step
exists, UI steps included; a service method alone does not count.

| Feature | Issue | Verdict per `@planned` scenario | Entry |
|---|---|---|---|
| KAL-API | #17 (closed) | all `@automated` | — |
| KAL-RUL | #5 (closed) | all `@automated` | — |
| KAL-FND | #13 | **003 implemented → `@automated`**; 002 partial (target typed by hand, 90-day average) | `funds-reserve-derived-target` |
| KAL-REC | #7 | **001 implemented → `@automated`** (When-step reworded to the real panel); 002, 004 missing | `recurring-to-planned` |
| KAL-CMP | #6 | **003 implemented → `@automated`**; 001, 002 partial | `budgets-plan-comparisons-gaps` |
| KAL-PID | #1 | 001, 002 partial — the scenario's own Lidl pair is not detected; merge cannot rename | `payees-merge-suggestions-gaps` |
| KAL-SUB | #8 | 002 partial (code gives 59.85, not 59.99); 004 partial | `subscriptions-panel-gaps` |
| KAL-DBT | #14 | 001 partial (no transaction link); 004 missing | `debts-ledger-link` |
| KAL-TRF | #4 | 001 missing; 002, 003 partial | `transfers-manual-pairing` |
| KAL-GOL | #12 | 001, 002, 004 partial; 003 missing | `funds-savings-goals` |
| KAL-IRR | #10 | 001–005 missing (container only) | `funds-irregular-items` |
| KAL-QIK | #2 | 001, 002 partial; 003 missing | `transactions-quick-entry-flow` |
| KAL-ANR | #9 | 001 partial; 002, 003 missing | `budgets-annual-review` |
| KAL-INV | #15 | 001–004 missing — **greenfield**, not "partial" as the 2026-07-07 table said (no holding/investment model; `Asset` is a physical item) | issue #15 |
| KAL-GFT | #11 | 001–003 missing, greenfield | issue #11 |
| KAL-AIN | #16 | 001, 002 missing, greenfield | issue #16 |

Decisions:
- **Gap entries are plans in the repo, not GitHub issue checkboxes.**
  Editing issue bodies is outward-facing and goal mode cannot ask; the
  criterion allows either. Each plan names its issue, so the owner can
  paste the plan link into the issue. Greenfield features need no entry
  beyond their issue: their `@planned` tags do not misrepresent code.
- **Retag only with a test.** The three retagged scenarios got e2e tests
  (`test_reserve_funds.py::test_dashboard_warns_when_reserve_is_below_target`,
  `test_subscriptions.py::test_stable_monthly_payment_is_detected`,
  `test_budget_comparisons.py::test_copy_previous_month_then_adjust_two_categories`).
  No `@manual` retags: nothing was verified by hand.
- FND-003's test asserts the warning row's title only — the wide
  dashboard renders `wizard_actions` as a banner without the "% funded"
  body. The widget caps rows at `MAX_ROWS = 12`; enough higher-severity
  items could hide the warning (noted, not changed: out of scope).
- Test-only helper `list_budgets` added to `tests/e2e/seed_helpers.py`
  (reads `GET /api/v1/budgets/`). No `src/` file touched.
- Cross-cutting finding sent to the chore inbox: fund balances read
  `Account.balance`, which no transaction moves
  (`AccountService.adjust_balance` has no caller). It blocks GOL-002 and
  IRR-004/005.
- Executable acceptance criteria were added beside the `[manual]` one so
  the gate checks the retags and entries, not just prose.
- Recommended-sequence steps 2 (re-milestone) and the issue edits are
  the owner's: the plans index in `docs/plans/README.md` lists every gap
  plan with its issue number.

