---
plan_id: budgets-api-realization
title: Budgets REST API — realization, range summary, copy-forward, bulk upsert
area: api, budgets
effort: medium
status: draft
roadmap_ref: ../roadmap.md
---

# Budgets REST API — realization, range summary, copy-forward, bulk upsert

## Intent
`/api/v1/budgets` only does row CRUD: list, upsert one row, get, put and delete. A script
(or Claude) that wants to answer "how am I doing against budget this month / this year"
has to pull every budget row and every transaction and re-implement the realization
maths itself: the expense-only actuals, internal transfers excluded, loan-linked
transactions excluded, split lines attributed. It would get that wrong. To start a new
month it has to copy the rows one POST at a time. `BudgetService` already does all of
this for the Budgets page: `realization_for_month`, `range_summary`, `copy_forward` and
`bulk_upsert`. Expose them through the API with typed response schemas, so a client sees
the same numbers the Realization tab shows.

## Scope

### Read endpoints
- `GET /budgets/realization?year=&month=&as_of=` → `BudgetRealizationResponse`.
  Thin wrapper over `BudgetService.realization_for_month(year, month, today=as_of)`.
  `month` is 1–12 and required, and `year` is 2000–2100 and required. `as_of` is an
  optional `date` that defaults to today. It sets `elapsed_pct` and the pace status, and
  it makes the endpoint deterministic for tests and for "how did March end" queries.
  Rows keep the service's order: worst pace first (over → warning → on_track).
  Totals come from `RealizationTotals.of(rows)`, the same figures the page's stat cards
  and Total row show.
- `GET /budgets/summary?start=&end=` → `BudgetSummaryResponse`. Thin wrapper over
  `BudgetService.range_summary(start, end)`. This is the year-to-date or any-range
  question (`start=2026-01-01&end=2026-12-31` for a year). Rows are sorted by category
  name, as the service returns them. The description must say what the service does:
  budget amounts count whole months for every month the range touches, and actuals count
  only the dates inside the range.
- `end < start` → 422. `range_summary` raises
  `ValidationError("…", code="invalid_date_range")`. The check goes in the service, not
  the route, so the error comes back in the standard envelope. The views always pass an
  ordered range (`date_range_for_key`), so they are unaffected.

### Write endpoints
- `POST /budgets/copy-forward` (`BudgetCopyForwardRequest`) → 200
  `BudgetWriteCountResponse {written}`. Wraps `BudgetService.copy_forward(from_year,
  from_month, to_year, to_month, overwrite=…)`. The default `overwrite=false` keeps a
  target-month amount that already exists, the same behaviour as the Plan tab's "Copy
  last month's plan into" button. If the source and target month are the same, the
  request schema returns 422.
- `copy_forward` is re-routed through `bulk_upsert`. Today it calls `upsert` once per
  row: each call does a select-then-insert and its own commit. So the copy is not
  atomic, and two overlapping copies into an empty month can hit
  `uq_budget_category_period` and return a 500. After the change it builds the
  `BudgetCreate` list (same filter: skip existing categories unless `overwrite`) and
  makes one `bulk_upsert` call, which is one `ON CONFLICT` statement. A source month
  holds at most one row per category (`uq_budget_category_period`), so `bulk_upsert`'s
  duplicate-summing never fires. The return value is unchanged: rows written, 0 for an
  empty source. Its two existing callers, `views/budget_plan/toolbar.py` and
  `MonthlyReadinessService`, see no behaviour change.
- `POST /budgets/bulk` (`BudgetBulkUpsertRequest {entries: list[BudgetCreate]}`, 1–1000
  entries) → 200 `BudgetWriteCountResponse {written}`. Wraps
  `BudgetService.bulk_upsert`. This is safe now: budget-bulk-upsert-concurrency landed on
  `main` (commits d1559a63 and 4701ce04, `on_conflict_do_update` on
  `uq_budget_category_period`). The description must state the service's contract:
  duplicate `(category_id, month, year)` entries **sum**, and `written` counts distinct
  keys.
- An unknown `category_id` in a bulk request → 422 `code="unknown_category"`, and no row
  is written. Today an unknown id becomes a FK `IntegrityError`, which reaches the
  catch-all handler as a 500. Add one `select(Category.id).where(Category.id.in_(…))`
  check at the top of `bulk_upsert`, before the insert. `YearlyPlanService.apply` only
  passes real category ids, so it is unaffected.

### Schemas (`src/kaleta/schemas/budget.py`)
The service returns dataclasses. Each response schema has
`model_config = ConfigDict(from_attributes=True)`, so it reads the dataclass fields and
`@property`s directly (`remaining`, `status`, `pace_delta`, `percent_used`,
`over_budget`, `RealizationTotals.used_pct`). No mapping code is written by hand.

- **Enums move down a layer.** `RealizationStatus` and `RealizationNoteKind` move from
  `services/budget_service.py` to `schemas/budget.py`. `budget_service.py` imports them
  back, so `from kaleta.services.budget_service import RealizationStatus` keeps working
  for `views/budgets/constants.py` and `tests/unit/views/test_realization_note.py`.
  `kaleta.schemas` sits below `kaleta.services` in the import-linter `layers` contract,
  so a schema cannot import them from the service. AGENTS.md (Working Agreement §10)
  rules out a bare `str` instead.
- `RealizationNoteResponse`: `kind: RealizationNoteKind`, `date: date`,
  `amount: Decimal`.
- `BudgetRealizationRow`: this schema already exists and is unused. Rework it to:
  `category_id`, `category_name`, `parent_id: int | None`, `parent_name: str | None`,
  `planned`, `actual`, `remaining: Decimal`, `elapsed_pct: float`,
  `used_pct: float | None`, `pace_delta: float | None`, `status: RealizationStatus`,
  `note: RealizationNoteResponse | None`.
  **`used_pct` and `pace_delta` are `None` for unplanned spending.** The service sets
  `used_pct = float("inf")` when `planned == 0` and `actual > 0`. Infinity is not valid
  JSON (Starlette's `JSONResponse` dumps with `allow_nan=False`), so passing it through
  would give a 500. A `field_validator(mode="before")` maps a non-finite float to
  `None`. `status` is still `over` for such a row, as the service computes it.
- `BudgetRealizationTotals`: `planned`, `actual`, `remaining: Decimal`,
  `used_pct: float`, `over: int`, `rows: int`. Read from `RealizationTotals`.
- `BudgetRealizationResponse`: `year: int`, `month: int`, `as_of: date`,
  `totals: BudgetRealizationTotals`, `categories: list[BudgetRealizationRow]`.
- `BudgetSummaryRow`: `category_id`, `category_name`, `budget_amount`,
  `actual_amount`, `remaining: Decimal`, `percent_used: float`, `over_budget: bool`.
  Read from `CategoryBudgetSummary`.
- `BudgetSummaryResponse`: `start: date`, `end: date`,
  `categories: list[BudgetSummaryRow]`, plus `@computed_field`s `budget_total`,
  `actual_total` and `remaining_total` (Decimal sums over `categories`).
- `BudgetCopyForwardRequest`: `from_year`, `to_year` (2000–2100), `from_month`,
  `to_month` (1–12), `overwrite: bool = False`. A `model_validator` rejects source ==
  target.
- `BudgetBulkUpsertRequest`: `entries: list[BudgetCreate] = Field(min_length=1,
  max_length=1000)`. The upper bound stays well below the ~8000-row asyncpg bind cap
  noted in `bulk_upsert`.
- `BudgetWriteCountResponse`: `written: int`.

### Router
- The four new routes are declared in `src/kaleta/api/v1/budgets.py` **before**
  `GET/PUT/DELETE /{budget_id}`. Otherwise `/budgets/realization` matches
  `/{budget_id}` and fails int validation with a 422. Every handler takes
  `session: AsyncSession = Depends(get_session)` from `kaleta.api.deps`, and every
  route has a `summary` and a `description`.

### Scenario (paste into `docs/bdd.md`, Feature: Public API, after KAL-API-009)

```gherkin
  KAL-API-017 @automated
  Scenario: Check budget realization and carry a month forward through the API
    Given a valid API bearer token
    And expense categories "Czynsz", "Jedzenie", "Rozrywka" and "Prezenty"
    And April 2026 budgets of 2000.00 for "Czynsz", 1200.00 for "Jedzenie" and 300.00 for "Rozrywka"
    And a March 2026 budget of 1000.00 for "Jedzenie"
    And April 2026 expenses of 2000.00 "Czynsz" on 2026-04-01, 450.00 "Jedzenie" on 2026-04-05, 360.00 "Rozrywka" on 2026-04-10, 150.00 "Jedzenie" on 2026-04-12 and 190.00 "Prezenty" on 2026-04-14
    And expenses of 700.00 "Jedzenie" on 2026-03-10 and 999.00 "Jedzenie" on 2026-05-02
    When I GET /api/v1/budgets/realization?year=2026&month=4&as_of=2026-04-15
    Then the response is 200 with the categories in the order "Prezenty", "Rozrywka", "Czynsz", "Jedzenie"
    And "Prezenty" is over with planned 0.00, actual 190.00 and used_pct null
    And "Rozrywka" is over with planned 300.00, actual 360.00, remaining -60.00 and used_pct 120.0
    And "Czynsz" is warning with actual 2000.00 and used_pct 100.0
    And "Jedzenie" is on_track with actual 600.00, remaining 600.00 and used_pct 50.0
    And every row has elapsed_pct 50.0
    And the totals are planned 3500.00, actual 3150.00, remaining 350.00, used_pct 90.0, over 2 and rows 4
    When I GET /api/v1/budgets/summary?start=2026-03-01&end=2026-04-30
    Then the categories are "Czynsz" 2000.00 spent of 2000.00, "Jedzenie" 1300.00 of 2200.00, "Prezenty" 190.00 of 0.00 and "Rozrywka" 360.00 of 300.00
    And the totals are budget 4500.00, actual 3850.00 and remaining 650.00
    Given a May 2026 budget of 250.00 for "Rozrywka"
    When I POST /api/v1/budgets/copy-forward from 2026-04 to 2026-05
    Then the response is 200 with written 2
    And May 2026 holds "Czynsz" 2000.00, "Jedzenie" 1200.00 and "Rozrywka" 250.00
    When I POST the same copy with overwrite true
    Then the response is 200 with written 3 and May 2026 "Rozrywka" is 300.00
    When I POST /api/v1/budgets/bulk with June 2026 entries "Czynsz" 2000.00 and "Jedzenie" 1100.00
    Then the response is 200 with written 2 and June 2026 holds exactly those two budgets
    And a bulk request with an unknown category_id is 422 and writes nothing
    And a copy whose source and target month are the same is 422
    And a summary whose end is before its start is 422
```

How the literals follow from the code, for the implementer:
- `elapsed_pct` = 15/30 × 100 = 50.0, because April has 30 days.
- The sort key is `(status, -pace_delta, name)`. Prezenty's `pace_delta` is ∞, so it
  sorts ahead of Rozrywka (70.0) in the over bucket.
- Czynsz is at 100.0 % against 50.0 elapsed. 100 is not > 100, so it is not over; it is
  > 50 + 5, so it is warning.
- Totals: `used_pct` = 3150 / 3500 × 100 = 90.0. Rozrywka and Prezenty are the two over.
- The summary's Jedzenie budget is 1000 + 1200. Its actual is 700 + 450 + 150. The May
  999.00 falls outside the range.

### Out of scope
- **Everything in budgets-plan-unification.** That plan is view-only: one `/budgets`
  page with Plan and Realization tabs, the `/budget-plan` redirect, a shared month
  selector, the edit-pencil jump and keyboard shortcuts. Slice 1 is merged (382a3f40).
  It defines no API and keeps "the editor's model" unchanged, so these endpoints neither
  overlap it nor expose anything it replaces. No view file is touched here.
- `load_annual_plan_grid` / `AnnualPlanGrid` / `YearPlanSlice`. This is the Plan tab's
  presentation grid (override flags, reference years, "show actual row"). Its shape
  follows the Plan panel, which the later budgets-plan-unification slices are still
  reworking. A frozen API contract on it would pin that view.
- `actuals_by_category_month`. It only feeds the grid above. A script gets the same
  per-month answer from `/budgets/summary` with one-month bounds.
- `monthly_summary`. It is `range_summary` over the month's first to last day.
  `/budgets/summary?start=…-01&end=…-<last>` returns the identical rows, and
  `/budgets/realization` is the richer month answer, so a third endpoint would duplicate
  both.
- `list_for_year`. `GET /budgets?year=` already returns a year's rows
  (budgets-api-year-filter, KAL-API-007).
- `YearlyPlanService` (Budget Builder plan rows, `apply`) and `AnnualReviewService`. They
  are separate domains (the yearly plan's income/fixed/variable/reserve lines, and the
  year-end review). Their writes fan out into many budget rows. Each would need its own
  plan and scenario, not a ride-along here.
- `delete_all_for_category_year`, the income side of realization (the service only
  counts expense actuals), checks on category type for budget rows, and any change to the
  existing five budget routes. The pre-existing `POST /budgets/` → 500 on an unknown
  category goes to the chore inbox, not this branch.

## Acceptance criteria
- `uv run pytest tests/integration/test_api_budget_realization.py -q`
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`
- `uv run pytest tests/integration/test_budgets.py tests/integration/test_budget_bulk_upsert_concurrency.py tests/unit/services/test_budget_service.py tests/unit/services/test_monthly_readiness_service.py tests/unit/views/test_realization_note.py -q`
- `grep -c "KAL-API-017" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- Tests in the new module, each with a `Covers: KAL-API-017` docstring. Expected values
  are the scenario's literals, never computed by calling `BudgetService`. Data is set up
  through the API (`create_category`, `create_account`, `transaction_payload`,
  `budget_payload` from `tests/integration/conftest.py`):
  - test_realization_for_april_matches_the_scenario: order, per-row status, `used_pct`
    (including `null` for Prezenty), `remaining`, `elapsed_pct`, `note` null, and the
    totals.
  - test_realization_of_an_empty_month_is_zero_totals: 200, `categories == []`, totals
    0.00 / `used_pct` 0.0 / `over` 0 / `rows` 0.
  - test_realization_rejects_month_13_and_missing_year: both 422.
  - test_summary_march_to_april_matches_the_scenario: rows by name and the three totals.
  - test_summary_end_before_start_is_422: `code == "invalid_date_range"`.
  - test_copy_forward_keeps_existing_then_overwrites: written 2, then written 3, with the
    May amounts read back through `GET /budgets?year=2026&month=5`.
  - test_copy_forward_from_an_empty_month_writes_nothing: written 0.
  - test_copy_forward_same_month_is_422.
  - test_bulk_upsert_writes_june: written 2, rows read back.
  - test_bulk_upsert_unknown_category_is_422_and_writes_nothing: `code ==
    "unknown_category"`, June still empty afterwards.
  - test_bulk_upsert_empty_entries_is_422.
  - test_openapi_gives_every_new_budget_operation_a_summary: asserted on
    `app.openapi()` for the four new paths.
- A unit test in `tests/unit/services/test_budget_service.py` covers the copy_forward
  re-route: copy_forward makes exactly one `bulk_upsert` call and returns the same count
  as before.

## Touchpoints
- `src/kaleta/api/v1/budgets.py`: four new routes, declared before `/{budget_id}`.
- `src/kaleta/schemas/budget.py`: the two enums move here; new request and response
  schemas; `BudgetRealizationRow` reworked.
- `src/kaleta/services/budget_service.py`: imports the enums from schemas;
  `range_summary` checks the date range; `bulk_upsert` checks for unknown categories;
  `copy_forward` goes through `bulk_upsert`.
- `src/kaleta/views/budgets/constants.py`: read only. It keeps importing
  `RealizationStatus` from the service through the re-import, so no edit.
- `tests/integration/test_api_budget_realization.py` (new),
  `tests/unit/services/test_budget_service.py` (one copy_forward test).
- `docs/bdd.md`: KAL-API-017 under Feature: Public API.

## Open questions
- **Should the realization endpoint accept `as_of`?** Default: **yes**, an optional
  `date` passed to the service's existing `today=` keyword. Without it the test literals
  would depend on the wall clock, and a script could not ask how a past month ended
  mid-month.
- **How should infinite `used_pct` / `pace_delta` be represented?** Default: **`null`**
  through a before-validator. Leave `status` as computed (`over`). Do not clamp to 100 or
  to a sentinel number: a client must be able to tell "unplanned" apart from "exactly at
  plan".
- **Should the enums move to schemas, or should a parallel schema enum be defined?**
  Default: **move** `RealizationStatus` and `RealizationNoteKind` to
  `kaleta.schemas.budget` and import them back into `budget_service`. One enum, no
  drift, and no edits to the importers.
- **Should `copy_forward` be re-routed through `bulk_upsert` in this plan?** Default:
  **yes**. An API write that 500s when two calls overlap is not "safe", and the fix
  reuses the already-proven `ON CONFLICT` path with the same return contract. If an
  existing copy_forward test fails for a reason other than per-row commits, stop and
  record it in Implementation notes rather than loosening the test.
- **Should duplicate keys in `POST /budgets/bulk` be rejected instead of summed?**
  Default: **keep summing** (the service contract `YearlyPlanService.apply` relies on)
  and document it in the route description. Rejecting them would fork the service's
  semantics for one caller.
- **Should `POST /budgets/copy-forward` and `/bulk` return 200 or 201?** Default:
  **200 with `{written}`**. They are idempotent actions over existing keys, not the
  creation of one addressable resource.
- **What is the bulk entry cap?** Default: **1000** (≈83 categories × 12 months). Raise
  it only if a real plan needs more, and never past the asyncpg bind cap.
- **Is KAL-API-017 free?** Default: **yes, use it**. It was assigned when the plan was
  drafted (`main` then used up to KAL-API-009); if 017 is already taken on `main` when work starts, take the next
  free id and record that here.

## Implementation notes
