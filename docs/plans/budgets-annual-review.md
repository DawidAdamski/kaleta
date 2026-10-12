---
plan_id: budgets-annual-review
title: Annual review — guided year close on top of the yearly plan tooling
area: budgets
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#budgets
---

# Annual review — guided year close on top of the yearly plan tooling

Gap-closing plan for issue #9 (`KAL-ANR-001`…`003`), from
[`audit-planned-vs-code`](archive/audit-planned-vs-code.md).

## What exists (2026-09-23)

- No Annual Review page, route or wizard step.
- Building blocks: per-category yearly plan-vs-actual totals on
  `/budget-plan` (`PlanCategoryRow.total_planned/total_actual`);
  `YearlyPlanService` (payload, derive, diff, apply) works for any year,
  but `/wizard/budget-builder` is locked to the current year;
  `copy_forward` is month-to-month only.
- Subscriptions exist; irregular-fund items do not (see
  [`funds-irregular-items`](funds-irregular-items.md)).

## Scope

- **ANR-001** — review page, step 1: plan vs actual per category for the
  year (reuse the grid's totals).
- **ANR-002** — step 2: carry the year into next year with per-category
  % adjustments, applied through `YearlyPlanService.diff/apply` for
  `year + 1`.
- **ANR-003** — step 3: keep / adjust / drop for each subscription and
  irregular item. Depends on `funds-irregular-items` for the items;
  ship subscriptions first if that plan has not landed.

## Acceptance criteria

- `grep -cE "KAL-ANR-00[1-3] @automated" docs/bdd.md | grep -q '^3$'`
- `uv run python scripts/spec_coverage.py`

## Open questions

- New page or a mode of the budget builder? Default: a mode of the
  budget builder with a year selector — it already owns
  payload/diff/apply.

## Implementation notes

### Decisions

- **A page of its own, `/wizard/annual-review?year=`** (open question), not a mode of the
  budget builder. The builder edits one year's lines; the review compares a year with its
  budgets, writes the *next* year, and touches subscriptions and fund items, none of which
  the builder owns. It reuses the builder's machinery — the carry is a
  `YearlyPlanPayload` for `year + 1` that goes through `YearlyPlanService.diff/apply`, with
  the same confirm-the-diff step. A "Annual review" step joins the wizard's budget section.
  The year defaults to the current one, and a selector offers the five before it.
- **Step 1 — the year in numbers**: every expense category with a plan or a spend that
  year, planned (the year's `budgets` rows) against actual (`actuals_by_category_month`,
  the grid's figures), the difference, and the totals.
- **Step 2 — the carry**: per category, this year's planned total, a % adjustment
  (default 0), and next year's amount. The next year's payload is this year's, carried:
  income and reserve lines as they are, each fixed or variable line scaled by its
  category's %, and — where this year's budgets hold more for a category than its lines
  derive (budgets set on the grid by hand) — a variable line for the rest, scaled too. A
  category with a spend but no plan is not carried: a plan is something the user chose.
  When `year + 1` already has a yearly plan, the step says so before the diff: applying
  replaces it.
- **Step 3 — the commitments** (`irregular items exist now`, `funds-irregular-items` is
  merged): every active subscription and every item of every irregular fund, with its
  yearly cost, and keep / adjust / drop. Keep changes nothing; adjust sets the
  subscription's charge or the item's yearly amount; drop cancels the subscription today
  (`SubscriptionService.cancel`) or deletes the item. A subscription's yearly cost is its
  charge × 365 / its cadence in days, rounded to the grosz.
- **`AnnualReviewService`** owns the three steps' reads and the carry; the view only wires
  it.
- **The wizard lists it** in its budget section ("Annual review", after the scenarios), so
  the index (artboard `3d`) gains one row; its routes test covers the link.
- **Tests**: `tests/integration/test_annual_review.py` (`KAL-ANR-001`…`003`, and the carry
  keeping this year's lines — a fixed line moved by its category's %, one without a
  category carried as is, no extra line where the lines already derive the budgets, and
  "replaces" once next year has a plan); `tests/e2e/test_annual_review.py` walks the three
  steps on 2021, a year no other e2e test plans.

### After review

- **A % is applied on leaving its field** (or Enter), not per keystroke — the redraw
  rebuilt the input being typed in. It goes down to −100% (the field's minimum; the
  service refuses below, a `ValidationError`, and a test pins both).
- **The year comes from the selector's own range** (the current year and the five before
  it); a `?year=` outside it falls back to the current year rather than a value the
  selector does not hold.
- **"Planned this year" in the carry** is the larger of the budgets and what this year's
  lines derive: the yearly plan's lines are the user's intent and carry as written, and
  budgets set above them on the grid carry as an extra line. A category *lowered* on the
  grid below its lines carries its lines — lower the line in the budget builder to carry
  less. (Test: several lines of one category plus a raise on the grid, moved by one %.)
- **Known limits, kept**: budgets set by hand carry as one yearly line, spread evenly by
  the yearly plan — a December-heavy category keeps its total, not its shape; and applying
  replaces next year's *plan*, while a next-year budget cell the carried plan does not
  derive stays (as with the budget builder, `bulk_upsert`). Items of an archived irregular
  fund are not asked about: archived is the user's "this fund is done".
- **Tests** gained the scheduled cancellation that is not asked about.
