---
plan_id: credit-first-class
title: Credit — first-class module (cards + loans)
area: credit
effort: large
status: draft
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
