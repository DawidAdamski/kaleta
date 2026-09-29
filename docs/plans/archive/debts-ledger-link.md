---
plan_id: debts-ledger-link
title: Debt tracking — link a loan to its transfer, keep loans out of spending
area: credit
effort: medium
status: archived
archived_at: 2026-09-29
roadmap_ref: ../../roadmap.md#credit
---

# Debt tracking — link a loan to its transfer, keep loans out of spending

Gap-closing plan for issue #14 (`KAL-DBT-001`, `KAL-DBT-004`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md). `KAL-DBT-002` and
`KAL-DBT-003` are `@automated`.

## What exists (2026-09-23)

- `/wizard/personal-loans`: add loan dialog → `PersonalLoanService.
  create_loan`; outstanding balance per person; repayments.
- `PersonalLoan` has **no transaction FK**; repayments create a new
  mirror transaction instead of linking an existing one.
- No report, dashboard widget or summary knows about loans.

## Scope

- **DBT-001** — `PersonalLoan.transaction_id` (nullable) + migration;
  the dialog picks an existing transaction ("yesterday's transfer");
  repayments may link an existing transaction too.
- **DBT-004** — a transaction linked to a loan is excluded from expense
  totals and shown under "Loans" in the monthly summary / money flow.

## Acceptance criteria

- `grep -qE "KAL-DBT-001 @automated" docs/bdd.md`
- `grep -qE "KAL-DBT-004 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Exclusion mechanism: flag on the transaction vs join through the loan.
  Default: join — one source of truth, no second flag to keep in sync.

## Implementation notes

- **Exclusion mechanism (open question):** took the default — join through
  the loan. `kaleta.services.loan_links.loan_linked_transaction_ids()` is the
  single source: the union of `PersonalLoan.transaction_id` and
  `PersonalLoanRepayment.linked_transaction_id`, NULLs filtered so it is safe
  inside `NOT IN`. No flag on `Transaction`.
- **Repayments count as loan money too.** A transaction linked as a
  repayment (either linked to an existing one or mirrored via "Mirror as
  transaction on…") is excluded from income/expense like the principal.
  Money coming back from Marek is not income. This changes the mirrored
  repayment's effect on reports — before, it counted as income under the
  picked category.
- **Model:** `personal_loans.transaction_id` nullable FK →
  `transactions.id` `ON DELETE SET NULL`, unique
  (`uq_personal_loans_transaction_id`): one transaction moves one loan's
  principal. The same migration (`p0q1r2s3t4u5`, no backfill) makes
  `personal_loan_repayments.linked_transaction_id` unique
  (`uq_personal_loan_repayments_linked_transaction_id`) — mirrors always
  created their own transaction, so existing rows already comply.
- **Races:** both link paths commit through `_commit_link`, which turns the
  unique-constraint `IntegrityError` into the same `ConflictError`. A
  principal and a repayment racing for one transaction sit in two tables
  and are only caught by the pre-check — accepted, it needs two users
  saving the same transfer in the same instant.
- **Service rules:** linking a missing transaction → `NotFoundError`; one
  already linked to any loan or repayment → `ConflictError`
  (`loan_transaction_taken`); a repayment that both links an existing
  transaction and asks for a mirror → `ValidationError`
  (`repayment_link_ambiguous`), also caught earlier by
  `parse_repayment_form`.
- **Picker:** `PersonalLoanService.list_link_candidates` — the 200 most
  recent non-internal, not-yet-linked transactions (the select filters as
  you type); the loans' current links are always added so an edit keeps
  them. 200 rather than 50 because a shared e2e DB (and a busy real ledger)
  easily has 50 rows dated today, which pushed "yesterday's transfer" off
  the list. The new-loan and repayment pickers never offer another loan's
  principal. Picking a transaction on a fresh loan fills the principal.
- **Where "Loans" shows (DBT-004):** the Income Statement report (monthly
  summary) gets a "Loans" table (lent or repaid / borrowed or paid back),
  and `IncomeStatement.loans_out` / `loans_in`. Money Flow draws `in:loans`
  / `out:loans` nodes in both lenses. Its surplus/deficit node balances the
  pool including loan cash, while `total_in` / `total_out` / `net` (the
  KPIs and API) stay income/expense only.
- **ReportService scope:** exclusion added to every income/expense
  aggregate (`_month_summary` → dashboard month KPIs and safe-to-spend,
  trailing spend, `cashflow_last_n_months`, `top_merchants`, YoY, YTD,
  `_sum_by_category` → income statement, spending by category, budget
  variance). Left alone: `_net_flow_since` (balance delta — loan cash really
  moved the balance), `recent_transactions` and `largest_transactions`
  (listings, not totals). Other services are out of this plan's scope and
  went to `chores.md`.
- `alembic check` shows index drift on `import_runs` / `import_rules` /
  `categorisation_rules` that predates this plan; logged in `chores.md`.
- **E2e helper fix (test-only, own commit):** the two new e2e tests seed
  categories that sort just before `test_quick_entry`'s
  "Spozywcze Qik E2E". That put the option in the virtual list's off-screen
  buffer, where Playwright's scroll-into-view click detached it on every
  retry. `tests/e2e/ledger.py::pick_open_menu_option` now dispatches the
  click on the found option. Full suite: 196 passed.

## Implementation

Landed on 2026-09-29 (PR #159).

| SHA | Author | Date | Message |
|---|---|---|---|
| `d775fe6` | Dawid Adamski | 2026-09-29 | Merge pull request #159 from DawidAdamski/plan/debts-ledger-link |

**Files changed:**
- alembic/versions/p0q1r2s3t4u5_add_personal_loan_transaction_link.py
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/debts-ledger-link.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/models/personal_loan.py
- src/kaleta/schemas/personal_loan.py
- src/kaleta/services/loan_links.py
- src/kaleta/services/money_flow_service.py
- src/kaleta/services/personal_loan_service.py
- src/kaleta/services/report_service.py
- src/kaleta/views/personal_loans/dialogs.py
- src/kaleta/views/personal_loans/helpers.py
- src/kaleta/views/personal_loans/page.py
- src/kaleta/views/personal_loans/rows.py
- src/kaleta/views/reports_canned/income_statement.py
- src/kaleta/views/reports_canned/money_flow.py
- tests/e2e/ledger.py
- tests/e2e/seed_helpers.py
- tests/e2e/test_debt_tracking.py
- tests/unit/services/test_loan_ledger_link.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
