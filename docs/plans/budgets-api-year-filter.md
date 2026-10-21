---
plan_id: budgets-api-year-filter
title: GET /api/v1/budgets honours ?year= on its own
area: budgets
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#budgets
---

# GET /api/v1/budgets honours ?year= on its own

## Intent
`GET /api/v1/budgets/?year=<Y>` is documented to "filter by year", but the
year was only applied when a `month` was also given. Every year's budgets
came back regardless of `?year=`, which breaks any client (and the
`budgets-annual-review` e2e) that lists a single year's plan over the API.

## Scope
- Fix `BudgetService.list` so a `year`-only call filters rows to that year.
- Keep `year` + `month` working, and keep the existing `month`-without-year
  behaviour (defaults the year to the current one).
- This bug: ONLY the list filter. Not in scope: the API route signature,
  other service methods, or any view.

## Acceptance criteria
- `uv run pytest tests/integration/test_budgets.py -q`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh`

## Touchpoints
- `src/kaleta/services/budget_service.py` — `BudgetService.list`
- `tests/integration/test_budgets.py` — new year-only filter test
- `docs/bdd.md` — KAL-API-007

## Open questions
None.

## Implementation notes
- The API route (`src/kaleta/api/v1/budgets.py`) already forwards both
  `year` and `month` to the service, so no route change was needed — the
  fix is entirely in `BudgetService.list`.
- Kept the "`month` requires `year`" contract by defaulting the year to the
  current year when a month is given without one, then applying year and
  month as independent `WHERE` clauses.
