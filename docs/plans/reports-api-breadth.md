---
plan_id: reports-api-breadth
title: Reports REST API — spending by category, top merchants, budget variance, YTD, YoY, safe to spend
area: api, reports
effort: medium
status: draft
roadmap_ref: ../roadmap.md
---

# Reports REST API — spending by category, top merchants, budget variance, YTD, YoY, safe to spend

## Intent
`/api/v1/reports` exposes three reports: `cashflow`, `income-statement` and `money-flow`
(`src/kaleta/api/v1/reports.py`). `ReportService` (`src/kaleta/services/report_service.py`)
already computes the figures a script, a home dashboard or Claude asks for most often:
where the money went, who got it, how the month did against the budget, how the year is
going and how much is left to spend today. None of them is reachable without the UI. This
plan exposes six existing service methods as read-only GET routes, each with a typed
Pydantic response. It needs no new service logic.

## Scope

### Which methods, and why
| Service method | Decision | Reason |
|---|---|---|
| `spending_by_category(start, end)` | **expose** | The most common question ("where did the money go"). |
| `top_merchants(start, end, limit)` | **expose** | Payee ranking. The transactions list cannot aggregate it. |
| `budget_variance(year, month)` | **expose** | Plan vs actual. A script would otherwise have to rebuild actuals with the split and loan rules `_sum_by_category` applies. |
| `ytd_summary(year)` | **expose** | One call for the year's headline: income, expenses, net, savings rate, top categories. |
| `yoy_comparison(year, basis)` | **expose** | Twelve month pairs. Would take 24 `income-statement` calls today. |
| `safe_to_spend(today=)` | **expose** | The dashboard's main figure. It includes planned transactions and projected subscription charges (`_committed_rest_of_month`), which a client cannot rebuild. |
| `cash_flow_statement(year, month)` | reject | It wraps `income_statement` and only renames its lists. `GET /reports/income-statement` returns the same data. |
| `savings_rate(months)` | reject | It is `cashflow_last_n_months` plus a ratio. `GET /reports/cashflow` returns income, expenses and net per month. |
| `current_month_summary()` | reject | A bare `(income, expenses)` tuple. That is `cashflow?months=1`. |
| `largest_transactions(days, limit, tx_type)` | reject | The window is "the last N days from today". It does not exclude loan-linked rows, and it orders by raw amount across types. Exposing it would freeze those quirks into the API. It needs service work first. |

### Routes (all in `src/kaleta/api/v1/reports.py`, all `Depends(get_session)` from `kaleta.api.deps`, each with a `summary=`)
1. `GET /reports/spending-by-category?start=&end=` → `SpendingByCategoryResponse`.
2. `GET /reports/top-merchants?start=&end=&limit=20` → `list[MerchantSpendResponse]`.
   `limit: int = Query(20, ge=1, le=100)`. The description says that only expense rows with a
   payee count (the service inner-joins `Payee`).
3. `GET /reports/budget-variance?year=&month=` → `BudgetVarianceResponse`. Same year/month
   bounds as `income-statement`.
4. `GET /reports/ytd?year=` → `YTDSummaryResponse`. `None` means the current year (to today).
5. `GET /reports/yoy?year=&basis=expense` → `YoYComparisonResponse`. `year` from 1971, because
   the service reads `year - 1`. `basis: TransactionType`. `transfer` raises
   `kaleta.exceptions.ValidationError` (422).
6. `GET /reports/safe-to-spend?as_of=` → `SafeToSpendResponse`. `None` means today.

### Date range and cap (routes 1 and 2)
- `start` inclusive, `end` exclusive, both required. This matches `money-flow` and the service.
- `MAX_REPORT_SPAN_DAYS = 366`, following `MAX_SUGGESTION_SPAN_DAYS` in
  `src/kaleta/api/v1/transfer_pairs.py`. A private `_check_range(start, end)` raises
  `ValidationError` when `end <= start` or the span is over the cap.

### Empty period
Every route returns 200 with empty rows and zero totals, never 404. `yoy` returns twelve
zero rows with `delta_pct: null`.

### Response schemas (new, in `src/kaleta/schemas/analysis.py`)
`src/kaleta/schemas/report.py` holds the saved-report schemas and is not touched. Money is
`Decimal`. Percentages are `Decimal | None` where the service property can be `None`,
returned unrounded. Routes copy the dataclass properties into the schemas, with no
arithmetic in the route.
`CategoryShareResponse`, `SpendingByCategoryResponse`, `MerchantSpendResponse`,
`BudgetVarianceRowResponse`, `BudgetVarianceResponse`, `YTDSummaryResponse`, `YoYRowResponse`,
`YoYComparisonResponse` (with `basis: TransactionType`), `SafeToSpendResponse`. Each mirrors
its dataclass in `report_service.py` (`SpendingByCategory`, `MerchantSpend`,
`BudgetVarianceReport`/`BudgetVarianceRow`, `YTDSummary`, `YoYComparison`/`YoYRow`,
`SafeToSpend`), including the computed properties (`share_pct`, `variance`, `variance_pct`,
`spent_pct`, `over_budget`, `savings_rate_pct`, `delta`, `delta_pct`, `per_day`, `spendable`).

### Scenario (paste into `docs/bdd.md`, Public API feature)
```gherkin
  KAL-API-016 @automated
  Scenario: Read spending, merchants, budget variance, YTD, YoY and safe-to-spend through the API
    Given a valid API bearer token and the account "mKonto" in PLN
    And the income category "Wynagrodzenie" and the expense categories "Czynsz", "Spożywcze" and "Paliwo"
    And budgets for March 2025 of 2000.00 for "Czynsz" and 800.00 for "Spożywcze"
    And these transactions on "mKonto":
      | date       | type    | amount  | category      | payee        |
      | 2024-03-10 | expense |  900.00 | Spożywcze     | Lidl         |
      | 2025-02-20 | expense |  150.00 | Paliwo        | Orlen        |
      | 2025-03-01 | income  | 6000.00 | Wynagrodzenie | ACME         |
      | 2025-03-03 | expense | 2000.00 | Czynsz        | Spółdzielnia |
      | 2025-03-05 | expense |  450.00 | Spożywcze     | Lidl         |
      | 2025-03-12 | expense |  520.00 | Spożywcze     | Biedronka    |
      | 2025-03-14 | expense |  300.00 | Paliwo        | Orlen        |
      | 2025-03-18 | expense |  130.00 | Spożywcze     | Lidl         |
    When I GET /api/v1/reports/spending-by-category from 2025-03-01 to 2025-04-01
    Then the rows are "Czynsz" 2000.00, "Spożywcze" 1100.00 and "Paliwo" 300.00, in that order
    And the total is 3400.00 and the share of "Czynsz" rounds to 58.82
    When I GET /api/v1/reports/top-merchants from 2025-03-01 to 2025-04-01
    Then the merchants are "Spółdzielnia" 2000.00 (1), "Lidl" 580.00 (2), "Biedronka" 520.00 (1) and "Orlen" 300.00 (1), in that order
    And with limit 2 only "Spółdzielnia" and "Lidl" are returned
    When I GET /api/v1/reports/budget-variance for 2025-03
    Then the rows are "Czynsz", "Spożywcze" and "Paliwo", in that order
    And "Czynsz" has planned 2000.00, actual 2000.00, variance 0 and is not over budget
    And "Spożywcze" has planned 800.00, actual 1100.00, variance -300.00, spent_pct 137.5 and is over budget
    And "Paliwo" has planned 0, actual 300.00, variance -300.00, no variance_pct and is not over budget
    And total_planned is 2800.00 and total_actual is 3400.00
    When I GET /api/v1/reports/ytd for 2025
    Then income is 6000.00, expenses 3550.00, net 2450.00 and the savings rate rounds to 40.83
    And the top expense categories are "Czynsz" 2000.00, "Spożywcze" 1100.00 and "Paliwo" 450.00
    When I GET /api/v1/reports/yoy for 2025 on the expense basis
    Then there are 12 rows; March is 3400.00 against 900.00 with delta 2500.00
    And February is 150.00 against 0 with no delta_pct
    And the totals are 3550.00 this year, 900.00 last year and a delta of 2650.00
    When I GET /api/v1/reports/safe-to-spend as of 2025-03-20
    Then income is 6000.00, spent 3400.00, committed 0.00 and free 2600.00
    And days_left is 12, per_day 216.67, trailing_avg_per_day 118.33 and it is spendable
    And a period with no transactions returns 200 with empty rows and zero totals
    And a range whose end is not after its start, or that spans more than 366 days, is refused with 422
    And basis "transfer" on /yoy is refused with 422
```

### Out of scope
- Saved reports (`SavedReportService`, `src/kaleta/schemas/report.py`).
- `cash_flow_statement`, `savings_rate`, `current_month_summary`, `largest_transactions`.
- Account, currency or category filters. No service method takes them; adding them is new service logic.
- Any change to `ReportService` or the three existing routes, including a span cap for `money-flow`.
- Rounding percentages, CSV/export, caching, any UI change.

## Acceptance criteria
- `uv run pytest tests/integration/test_api_reports.py -q`
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`
- `grep -c "KAL-API-016" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- Tests in the reports API module: the scenario test (`Covers: KAL-API-016`) seeds the
  scenario's data and asserts every literal, with percentages compared after quantizing to
  0.01. No expected value comes from calling `ReportService`. Further tests cover: an empty
  period on all six routes; range rejection (`end == start`, 368 days → 422; a 365-day
  calendar year → 200, in the error envelope); a transfer basis on yoy → 422; top-merchants
  limit 0 and 101 → 422; and every new operation in `app.openapi()` having a summary.

## Touchpoints
- `src/kaleta/api/v1/reports.py`: six routes, `MAX_REPORT_SPAN_DAYS`, `_check_range`.
- `src/kaleta/schemas/analysis.py`: the response schemas.
- `src/kaleta/services/report_service.py`: read only.
- `tests/integration/test_api_reports.py` (new), `docs/bdd.md` (KAL-API-016).

## Open questions
- **Scenario id?** Default: KAL-API-016. If it is taken on `main`, use the next free one and record it here.
- **Inclusive or exclusive `end`?** Default: exclusive, like `money-flow` and the service.
- **Span cap value?** Default: 366 days. Money-flow's missing cap goes to `docs/plans/chores.md`.
- **Round percentages?** Default: no. Return the service's Decimal; clients format.
- **`safe-to-spend` with a past `as_of`?** Default: yes, the service takes `today=`. If the
  payment-calendar sources fail for a past date, record it here and test with `as_of`
  omitted and amounts dated in the current month instead. Do not change the service.
- **Payees with the same name?** Default: reported as the service groups them (by payee id).

## Implementation notes
