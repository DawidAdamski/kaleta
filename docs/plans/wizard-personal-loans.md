---
plan_id: wizard-personal-loans
title: Wizard — Personal loans tracker
area: wizard
effort: medium
status: draft
roadmap_ref: ../product/financial-wizard.md#6-personal-loans
---

# Wizard — Personal loans tracker

## Intent

Money lent to (or borrowed from) friends and family is a common
headache — it lives outside the bank ledger and tends to be
forgotten. Give the user a simple tracker inside the wizard.

## Scope

- New wizard section "Personal loans".
- Entry form: counterparty, direction (I owe / they owe), amount,
  date opened, optional due date, notes.
- List view grouped by status (outstanding / settled) with totals.
- Partial repayments allowed — each repayment is a row under the
  loan, updating the remaining balance.
- Optional link: generate a matching Transaction when a repayment
  is recorded against a real account (opt-in per repayment).

Out of scope:
- Interest calculations.
- Automatic reminders / notifications (uses the notification
  infrastructure from `wizard-monthly-readiness`).

## Acceptance criteria

- Adding a loan creates a record with `status=outstanding`.
- Recording a repayment reduces `remaining` and flips `status` to
  `settled` when it hits 0.
- Totals on the section card: "you owe {X}", "they owe you {Y}".
- Deleting a loan cascades its repayments but never touches linked
  transactions.

## Touchpoints

- New models `PersonalLoan` + `PersonalLoanRepayment`.
- Alembic migration.
- `src/kaleta/services/personal_loan_service.py`.
- `src/kaleta/schemas/personal_loan.py`.
- `src/kaleta/views/wizard.py` — section card.
- Possibly a dedicated `src/kaleta/views/personal_loans.py` detail
  page when the card is expanded.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Should counterparty be a free-text string, or a typed entity the
  user can reuse? v1: typed entity (`Counterparty`) with autocomplete.
- Currency: inherit default-currency from settings; cross-currency
  loans deferred.

## Implementation notes

_(filled as work progresses)_
