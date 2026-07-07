---
plan_id: audit-planned-vs-code
title: Audit — @planned BDD features vs existing code (2026-07-07)
area: cross-cutting
effort: small
status: draft
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
