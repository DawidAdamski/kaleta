---
plan_id: credit-first-class
title: Credit — first-class module (cards + loans)
area: credit
effort: large
status: archived
archived_at: 2026-04-23
roadmap_ref: ../roadmap.md#credit
---

# Credit — first-class module

## Intent

Credit cards and consumer loans are treated as plain accounts today.
They have unique lifecycle features (statement cycle, minimum
payment, APR, utilization, amortisation) that deserve a dedicated
module surfacing the risks — especially overdue minimum payments or
high utilization.

## Scope

- Two new entity types, each backed by the existing `Account` model
  with a kind discriminator:
  - `CreditCard` profile: credit limit, statement day, payment due
    day, minimum-payment rule, APR.
  - `Loan` profile: principal, APR, term (months), start date,
    monthly payment.
- New Credit view:
  - List of credit-cards with utilization bar, current balance vs
    limit, next due date, minimum due.
  - List of loans with amortisation progress (bar or small schedule
    preview), remaining balance, next due date.
  - Status chips: on-time / grace / overdue.
- Amortisation calculator for loans (standard fixed-rate formula)
  generating a monthly schedule.
- Credit card utilization widget eligible for the Dashboard catalog.

Out of scope:
- Variable-rate loans.
- Credit-score fetching / external integrations.
- Dynamic APR changes mid-life — user edits the profile manually.

## Acceptance criteria

- Creating a credit-card account prompts for credit limit + cycle
  fields; these persist in the profile table.
- Utilization = current balance / limit, rendered as 0–100% with
  thresholds (green <30%, amber <70%, red ≥70%).
- Loan amortisation schedule rows sum (principal + interest) to the
  initial principal.
- Next-due date computed from cycle fields and current date.
- Overdue chip fires when current date > due date AND balance > 0
  (card) / scheduled payment not recorded (loan).

## Touchpoints

- New models `CreditCardProfile` and `LoanProfile`, FK to `Account`.
- Alembic migration.
- `src/kaleta/services/credit_service.py` — utilization,
  amortisation, next-due computation.
- `src/kaleta/schemas/credit.py`.
- New `src/kaleta/views/credit.py`.
- `src/kaleta/views/layout.py` — new nav entry.
- `src/kaleta/views/widgets/credit_utilization.py` — dashboard
  widget.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Minimum-payment rule: percent-of-balance with a floor? Start with
  `max(2% * balance, 30 PLN)` configurable per card.
- Should loans live in the same view as cards (tabs) or separate
  pages? v1: tabs inside `/credit`.

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-23.

| SHA | Author | Date | Message |
|---|---|---|---|
| `9f4e3d0` | Dawid | 2026-04-23 | feat(credit): first-class module for cards and loans |

**Files changed:**
- `src/kaleta/models/credit.py` (new — CreditCardProfile, LoanProfile)
- `src/kaleta/models/__init__.py` (exports)
- `alembic/versions/c7e9b3f1a2d5_add_credit_and_loan_profiles.py` (new migration, down_revision a4e9b2f1c6d8)
- `src/kaleta/schemas/credit.py` (new — CardView, LoanView, AmortisationRow, Create/Update/Response, CreditStatus enum)
- `src/kaleta/services/credit_service.py` (new — CRUD + pure helpers compute_monthly_payment / amortisation_schedule / compute_min_payment / next_due_date)
- `src/kaleta/services/__init__.py` (exports)
- `src/kaleta/views/credit.py` (new — /credit with tabs Cards / Loans, New dialogs)
- `src/kaleta/views/layout.py` (nav entry under Tools)
- `src/kaleta/views/dashboard_widgets.py` (new credit_utilization widget, half-width)
- `src/kaleta/main.py` (registers view)
- `src/kaleta/i18n/locales/en.json` (full credit.* block, nav.credit, dashboard_widgets.credit_utilization*)
- `src/kaleta/i18n/locales/pl.json` (full credit.* block, nav.credit, dashboard_widgets.credit_utilization*)
- `tests/unit/services/test_credit_service.py` (14 tests — pure-helper algebra + service CRUD flow)
- `docs/architecture.md` (ADR-029 + directory entries)
- `docs/tech-stack.md` (Credit row in UI features)
- `README.md` (Credit bullet)

**What shipped:**
- Two profile tables FK'd to Account. One credit-card profile or one loan profile per account, never both. Unique constraints enforce the 1:1 rule.
- Balance convention: credit accounts store negative values when money is owed; the view normalises to positive "amount owed" for display. Keeps NetWorth math unchanged.
- Utilization thresholds green <30% / amber <70% / red ≥70%. Status chips on-time / due-soon (≤5 days to due) / overdue.
- Minimum payment = max(pct × balance, floor), capped at balance — defaults 2% / 30 PLN, per-card override.
- Amortisation: `compute_monthly_payment` uses the standard fixed-rate annuity formula (Excel PMT equivalent); `amortisation_schedule` emits per-month rows where the last row absorbs rounding residue so Σprincipal_paid == principal exactly.
- Next-due calculation is cycle-aware: rolls to next month (and year) when today is past the due day.
- New /credit page with two tabs (Cards / Loans). Creating a card or a loan atomically spins up an Account (type=credit, negative balance) and the profile row.
- Dashboard widget `credit_utilization` (half-width) lists every card's utilization bar so the home page flags high-util cards at a glance.
- 14 unit tests covering: zero-APR monthly payment, standard PMT (10k@12% for 24mo → 470.73 matches Excel), schedule closure, min-payment (floor-wins / pct-wins / balance-capped), next-due across month-and-year boundaries, card listing with utilization tier, loan create persists monthly_payment, loan listing includes remaining_balance bounded by [0, principal], amortisation-via-service closes exactly.
- Verified live on dev DB: created a "Test Visa" with 5000 PLN limit → rendered card with 0% green utilization bar, next due 25.04.2026, 0.00 PLN min payment, on-time chip. Cleaned up after.

**Partial coverage / deferred:**
- Variable-rate loans — out of scope per plan.
- Credit-score fetching / external integrations — out of scope.
- Dynamic APR changes mid-life — profile fields are editable but history is not tracked; user edits replace the value wholesale.
- Overdue for loans via real transaction matching — `_loan_status` only reads the schedule position; "scheduled payment not recorded" fires as grace within 5 days of the due day but does not walk actual transactions to confirm. That would need a planned-transaction → actual-transaction match layer.
- Editing a card / loan from the view — only creation is wired. Edit and delete are future follow-ups (the service has update_card / update_loan ready).
- Amortisation schedule pagination — preview shows the first 6 rows + "+N more rows" note; a full expandable table is a polish item.
- Dashboard widget not auto-added to default layout — users opt in via the Customize dialog. Can flip it on by default in a follow-up if universally wanted.
