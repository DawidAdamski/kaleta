---
plan_id: budgets-plan-comparisons-gaps
title: Budget planning comparisons — previous month across the year boundary, past years while editing
area: budgets
effort: medium
status: archived
archived_at: 2026-09-27
roadmap_ref: ../../roadmap.md#budgets
---

# Budget planning comparisons — previous month across the year boundary, past years while editing

Gap-closing plan for issue #6 (`KAL-CMP-001`, `KAL-CMP-002`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md). `KAL-CMP-003` is
`@automated`.

## What exists (2026-09-23)

- `/budget-plan` single-year grid: a plan row and an "Actual" row per
  category for all twelve months — last month's actual sits beside the
  month being planned, *except* January (December is in last year's
  grid). The actual row hides when a category has neither plan nor
  actual. The only e2e (`test_budget_plan_page_shows_planned_and_actual_columns`)
  checks the "Actual" label, not a value.
- Year chips (today−4…today+1) show several years side by side — but
  compare mode is **read-only**, so you cannot plan July 2026 while
  looking at July 2024/2025.

## Scope

- **CMP-001** — January shows the previous December's actual; e2e
  asserts a seeded previous-month value in the row.
- **CMP-002** — editable current year with reference rows for chosen
  past years (actuals), instead of read-only compare mode.
- Coordinate with [`budgets-plan-unification`](../budgets-plan-unification.md),
  which moves this grid under `/budgets?tab=plan`; whichever lands
  second rebases.

## Acceptance criteria

- `grep -qE "KAL-CMP-001 @automated" docs/bdd.md`
- `grep -qE "KAL-CMP-002 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Past-year reference rows: actuals only, or plan too? Default: actuals
  only — the scenario asks for actuals and the grid is already dense.

## Implementation notes

- **Open question — reference rows: actuals only or plan too?** Took the
  default: actuals only. A reference row (`PlanReferenceRow`) carries one
  past year's twelve actuals and its total; plan figures of past years are
  not shown.
- **Which year is editable (CMP-002).** The latest selected year chip is
  the edited year; every earlier selected chip adds its actuals as a
  reference row under each category (`split_plan_years`). Selecting a
  single chip behaves exactly as before. This replaces the read-only
  compare mode entirely — `AnnualPlanGrid` lost `is_compare`,
  `compare_month_totals` and `compare_grand_total` and now carries
  `edit_year`, `reference_years` and one `year_slice`. The toolbar's
  copy-forward and the edit dialogs keep reading `state["edit_year"]`,
  which the chip toggle now sets to `max(years)`.
- **Reference rows only when a year spent something** on that category —
  a line of twelve dashes per year per category would double the height
  of an already dense grid for no information. The unit test
  `test_a_reference_year_without_spending_adds_no_row` pins this.
- **Where January's previous month lives (CMP-001).** The actual line's
  Month-column slot (left of January, empty on actual lines before) shows
  `Dec ’25 420` with a tooltip naming the year; the bottom Actual totals
  row does the same for the grid total. The service loads the year
  before the edited one (`prev_actual_map`, only December read) — one
  extra grouped query, shared with the reference years when it is one.
  A category whose only spending is last December still shows its actual
  line (`show_actual_row`).
- **E2e years are relative** (`CURRENT_YEAR - 2/-1`), not the scenario's
  literal 2024/2025: the year chips span today−4…today+1, so literal years
  would fall off the chips in a few years. The unit test uses the
  scenario's literal 2024/2025/2026 and amounts.
- **No artboard** is named by this plan, so rule 12's fidelity check does
  not apply; the new lines reuse the actual line's type scale and mono.
- `docs/adr/025` still says "year-over-year comparison"; it is a dated
  decision record and is left as written. `docs/tech-stack.md` updated.
- Coordination with `budgets-plan-unification` (still draft): it will
  rebase onto this grid.
- **Unrelated e2e fix, own commit.** The two new e2e tests seed two
  categories ("Food … CMP E2E") that sort ahead of the CSV import tests'
  categories. `tests/e2e/test_csv_import.py::_select_import_option`
  clicked the menu option directly, so in the full suite the option fell
  outside Quasar's rendered virtual-scroll slice and
  `test_wise_qif_renamed_upload_is_unknown_and_still_imports` timed out
  (twice on this branch, never on `main`, never when run alone). The
  helper now uses the existing scroll-aware `ledger.pick_open_menu_option`.
  No timeout or assertion changed.

## Implementation

Landed on 2026-09-27 (PR #155).

| SHA | Author | Date | Message |
|---|---|---|---|
| `c298243` | Dawid Adamski | 2026-09-27 | Merge pull request #155 from DawidAdamski/plan/budgets-plan-comparisons-gaps |

**Files changed:**
- docs/bdd.md
- docs/plans/budgets-plan-comparisons-gaps.md
- docs/tech-stack.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/services/budget_service.py
- src/kaleta/views/budget_plan/grid.py
- src/kaleta/views/budget_plan/toolbar.py
- src/kaleta/views/theme.py
- tests/e2e/test_budget_comparisons.py
- tests/e2e/test_csv_import.py
- tests/unit/services/test_budget_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
