---
plan_id: wizard-personal-loans
title: Wizard — Personal loans tracker
area: wizard
effort: medium
status: archived
archived_at: 2026-04-23
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

## Implementation

Landed on 2026-04-23.

| SHA | Author | Date | Message |
|---|---|---|---|
| `aac4620` | Dawid | 2026-04-23 | feat(wizard): Personal Loans tracker |

**Files changed:**

- `alembic/versions/d5b8a2e7c1f4_add_personal_loans.py`
- `src/kaleta/i18n/locales/en.json`
- `src/kaleta/i18n/locales/pl.json`
- `src/kaleta/main.py`
- `src/kaleta/models/__init__.py`
- `src/kaleta/models/personal_loan.py`
- `src/kaleta/schemas/personal_loan.py`
- `src/kaleta/services/__init__.py`
- `src/kaleta/services/personal_loan_service.py`
- `src/kaleta/views/personal_loans.py`
- `src/kaleta/views/wizard.py`
- `tests/unit/services/test_personal_loan_service.py`

**What shipped:**

- **Counterparty** — typed entity with unique-by-name + `upsert_counterparty` so the dialog accepts free-text and reuses existing rows.
- **PersonalLoan** — direction enum (`outgoing` = they owe me, `incoming` = I owe them), principal, currency (PLN default), `opened_at`, optional `due_at`, notes, status enum with `settled_at` timestamp; repayments are `cascade=all, delete-orphan`.
- **PersonalLoanRepayment** — amount, date, note, `linked_transaction_id` FK with `ondelete=SET NULL` so deleting a loan never touches the real ledger.
- **`record_repayment`** flips status to `SETTLED` when `principal − Σ repayments ≤ 0` and stamps `settled_at`; `delete_repayment` re-evaluates and reopens the loan when remaining balance grows back.
- **Optional "mirror as transaction on…"** per repayment: creates a real `Transaction` on the chosen account with the right type (`INCOME` for outgoing, `EXPENSE` for incoming) and description `"Personal loan repayment: {counterparty.name}"`.
- **`/wizard/personal-loans` view** — header with `they_owe_you` / `you_owe` totals, Add dialog (counterparty free-text + upsert, direction radio, amount/currency, opened/due dates, notes), Outstanding + Settled sections, per-loan row with remaining/principal, edit/repay/delete icon cluster, full repayment history inlined under each loan with per-row delete.
- **Wizard wiring** — new "loans" section (`cyan-7`, `handshake` icon), step `personal_loans` links to `/wizard/personal-loans`; `_STEPS` and `_STEP_ROUTES` updated.
- **11 unit tests** — CRUD, repayment → settled, delete repayment → outstanding, linked transaction types, totals split by direction, cascade delete, linked-tx preservation.

**Partial coverage / deferred:**

- **Interest calculations** — out of scope per plan.
- **Reminders / notifications** — plan noted these would hook into `wizard-monthly-readiness` notification infrastructure, which itself is not fully shipped.
- **Cross-currency loans** — v1 stores currency per loan (`String(3)`, PLN default) but totals aggregate without FX conversion; assumes all outstanding loans share a currency.
- **Repayment ↔ linked-transaction sync** — `SET NULL` keeps loan rows safe when a Transaction is deleted, but reconciliation is one-shot at creation time; later edits to the Transaction do not propagate back.
- **Counterparty autocomplete** — currently a plain `ui.input` with server-side upsert; typeahead against existing counterparties is a follow-up polish item.
- **Budget / category default on repayment mirror** — dialog exposes a category picker but offers no default; user selects manually every time.
