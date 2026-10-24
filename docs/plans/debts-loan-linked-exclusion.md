---
plan_id: debts-loan-linked-exclusion
title: Loan-linked transactions excluded from every spending/income reader
area: debts / reports
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Loan-linked transactions excluded from every spending/income reader

## Intent
A personal-loan principal or repayment moves cash but is not spending or
income — it is tracked under "Loans". `ReportService` and
`MoneyFlowService` already exclude loan-linked transactions (KAL-DBT-004),
but eight other income/expense readers still count them, so lending 400 to a
friend inflates budget actuals, the safety-fund burn rate, salary baselines
and forecasts. This plan applies the one canonical predicate everywhere a
figure means "spending" or "income" rather than "cash moved".

Parent / origin: chore `docs/plans/chores.md:295` and
`plan/debts-ledger-link` (which built the link and fixed the first two
readers).

## Scope

Apply the canonical predicate from
`src/kaleta/services/loan_links.py::loan_linked_transaction_ids()` — the same
one `report_service.py::_month_summary` and
`money_flow_service.py::_category_flows` use — at the 11 edit sites below.
Raw form: `Transaction.id.not_in(loan_linked_transaction_ids())`; over the
`categorised_flows` subquery: `flow.c.transaction_id.not_in(...)`.

1. **BudgetService** (`budget_service.py`), flow form — 3 sites:
   - `realization_for_month`
   - `range_summary` (`monthly_summary` delegates here — no separate edit)
   - `actuals_by_category_month`
2. **SavedReportService** (`saved_report_service.py`) — 2 sites, in the
   filter builders so all query variants are covered:
   - `_transaction_filters` (raw form)
   - `_flow_filters` (flow form)
3. **ForecastService** (`forecast_service.py`) — `forecast_account`
   training query (raw form).
4. **SalaryService** (`salary_service.py`) — `income_by_month` (raw form).
5. **UnplannedRadarService** (`unplanned_radar_service.py`) — `detect`
   (raw form).
6. **MonthlyReadinessService** (`monthly_readiness_service.py`) — `stage_2`
   `actual_stmt` (raw form).
7. **ScenarioService** (`scenario_service.py`) — `trailing_monthly_income`
   (raw form).
8. **ReserveFundService** (`reserve_fund_service.py`) —
   `trailing_monthly_expense` (raw form; covers `target_monthly_expense`
   and `derived_target`, which reuse it).

### Judgement calls (in scope)

- **ForecastService.** A one-off loan principal is a financing spike, not
  recurring income/expense. Excluding loan-linked transactions from the
  training series cleans the trend the forecaster learns, so the exclusion
  belongs here too.
- **SavedReportService.** The predicate is added in the two filter builders
  (`_transaction_filters` / `_flow_filters`) rather than at each call site,
  so every current and future query variant inherits it from one place.

### Not in scope (left untouched by design)

- **MonthlyReadinessService `stage_1`.** It counts *uncategorised*
  transactions (data-completeness), not an income/expense sum. A loan
  transaction that still needs a category is a real count; excluding it
  would hide work the user must do.
- **ReserveFundService transfer-mirroring helper** (`~L340`, selects
  `linked_transaction_id`). It mirrors a transfer, not a spending/income
  readout.
- **`categorised_flows_selectable()` itself.** The inverse loan-total
  queries (`_loan_rows`, `_loan_summary`) rely on the raw subquery, so the
  predicate stays at the N call sites rather than being pushed down.

## Acceptance criteria

- `uv run pytest tests/integration/test_loan_linked_exclusion.py -q`
- `uv run pytest tests/unit/services/test_loan_ledger_link.py -q`
- `grep -q "KAL-DBT-005" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run lint-imports`

## Touchpoints
- `src/kaleta/services/budget_service.py`
- `src/kaleta/services/saved_report_service.py`
- `src/kaleta/services/forecast_service.py`
- `src/kaleta/services/salary_service.py`
- `src/kaleta/services/unplanned_radar_service.py`
- `src/kaleta/services/monthly_readiness_service.py`
- `src/kaleta/services/scenario_service.py`
- `src/kaleta/services/reserve_fund_service.py`
- `docs/bdd.md` — new scenario KAL-DBT-005 (`Feature: Debt Tracking`)
- `tests/integration/test_loan_linked_exclusion.py` (new)
- `tests/unit/services/test_loan_ledger_link.py` (extended)

## Open questions
None — all resolved into the scope above.

## Implementation notes
- The helper returns a NULL-safe `Select[tuple[int]]` embedded as a
  `NOT IN` operand; each edit imports it exactly as `report_service.py` and
  `money_flow_service.py` do (`from kaleta.services.loan_links import
  loan_linked_transaction_ids`).
- KAL-DBT-005 uses round literals so the asserted figures are the scenario's
  own values: groceries actuals 120.00, salary baseline 3000.00, 3-month
  burn rate 40.00 (120.00 ÷ 3), what-if income baseline 1000.00 (3000.00 ÷ 3).
  The integration test seeds a 400.00 outgoing loan (tests the expense side)
  and a 900.00 borrowing (an incoming loan-linked income, tests the income
  side).
