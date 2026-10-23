---
plan_id: errors-i18n-funds-cohort
title: Localize reserve-fund, gift, salary & personal-loan error toasts
area: cross-cutting
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Localize reserve-fund, gift, salary & personal-loan error toasts

## Intent
A follow-up cohort slice of
[`errors-i18n-message-keys`](archive/errors-i18n-message-keys.md), which
shipped the carrier (`KaletaError.message_key` + `params`), the
`error_handling.resolve_toast_text` wiring, and migrated the first cohort
(payee identity / merge-undo); `errors-i18n-transactions` then migrated
`transaction_service`. This slice migrates the **funds / salary / debt
family** — four services — so a Polish session reads their toasts in Polish,
while logs, event capture and the API keep reading the English `exc.message`.

## Scope
Covers — each user-facing `KaletaError` raise in these four services gets a
`message_key` (+ `params` where the message interpolates), keeping the
existing English string byte-identical as the positional `message` fallback:
- `src/kaleta/services/reserve_fund_service.py` → `errors.reserve_fund.*`
- `src/kaleta/services/gift_service.py` → `errors.gift.*`
- `src/kaleta/services/salary_service.py` → `errors.salary.*`
- `src/kaleta/services/personal_loan_service.py` → `errors.personal_loan.*`
- The four new sub-blocks in `en.json` and `pl.json`, placed at the END of
  the `errors` object (after `transaction`).
- `docs/bdd.md`: `KAL-ERR-004` + a covering integration test
  (`tests/integration/test_error_i18n_funds_cohort.py`).

Does NOT cover:
- Any other service (each remaining service gets its own follow-up slice —
  the `chores.md` follow-up line stays open until all are done).
- Changing `code` values, control flow or any behaviour.
- The REST API error contract (still emits the English `message`).
- Localizing the `PersonalLoanFormError` dialog messages — that is a plain
  `Exception`, not a `KaletaError`, and is out of this carrier's scope.

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-004" docs/bdd.md`
- `uv run pytest tests/integration -k "error_i18n" -n 2 -m "not slow"`

## Touchpoints
- `src/kaleta/services/reserve_fund_service.py` — migrated raises.
- `src/kaleta/services/gift_service.py` — migrated raises.
- `src/kaleta/services/salary_service.py` — migrated raises.
- `src/kaleta/services/personal_loan_service.py` — migrated raises.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — `errors.reserve_fund.*`,
  `errors.gift.*`, `errors.salary.*`, `errors.personal_loan.*`.
- `docs/bdd.md` — `KAL-ERR-004`;
  `tests/integration/test_error_i18n_funds_cohort.py`.

## Open questions
- Resolved to plan defaults (no user input while armed).

## Implementation notes
- **Slice boundary.** This covers the four funds/salary/debt services only;
  the parent plan's "remaining services get their own follow-up slices" is
  honoured. The `chores.md` follow-up line stays unticked.
- **Per-service caller search (reachability).** Every migrated raise reaches
  a view (→ `notify_kaleta_error`) directly or through a view-called service.
  No raise was skipped.
  - **`ReserveFundService`** — callers: `views/safety_funds.py`
    (`contribute`, `close`, `update`, `archive`, `unarchive`, `delete`),
    `views/dashboard.py`, `api/v1/reserve_funds.py`, plus service callers
    (`annual_review_service`, `scenario_service`, `wizard_action_service`).
    The view calls `contribute`/`close` (which run `_goal` then `_move`) and
    `update`, so all 9 raises are user-facing. **Migrated 9, skipped 0.**
    Keys: `multiplier_required_for_spending_target`; `fund_not_found`
    (`{fund_id}`, two raise sites — `_goal` and the `close` deleted-between-
    steps race); `only_goal_contributes`; `goal_already_closed`;
    `goal_no_backing_account`; `account_to_itself`; `account_not_found`
    (`{account_id}`); `same_currency_required`. (8 keys over 9 raises.)
  - **`GiftService`** — callers: `views/gifts.py` (`update`, `delete`,
    `link_transaction`, `mark_not_bought`), `irregular_item_service`. All 7
    raises sit on view-reached methods. **Migrated 7, skipped 0.** Keys:
    `not_found` (`{gift_id}`, four raise sites); `transaction_not_found`
    (`{transaction_id}`); `only_expense_pays`; `transaction_pays_another`.
    (4 keys over 7 raises.)
  - **`SalaryService`** — callers: `views/wizard_salary.py` (`propose`,
    `create_salary_plan`). `propose` runs `income_by_month`. All 4 raises are
    user-facing. **Migrated 4, skipped 0.** Keys: `window_at_least_one_month`,
    `override_not_negative`, `source_target_differ`, `account_not_found`
    (`{account_id}`). (4 keys, 4 raises.)
  - **`PersonalLoanService`** — callers: `views/personal_loans/dialogs.py`
    (`record_repayment`, `delete_loan`, `delete_repayment`, and the loan
    create/update path), `views/personal_loans/page.py`,
    `api/v1/personal_loans.py`, `wizard_action_service`. The repayment and
    loan dialogs reach `record_repayment`/`create_loan`/`update_loan`, which
    run `_check_linkable`/`_commit_link`. All 4 `KaletaError` raises are
    user-facing. **Migrated 4, skipped 0.** Keys: `link_ambiguous`;
    `transaction_taken` (`{transaction_id}`, two raise sites — `_commit_link`
    and `_check_linkable`, both keep their `code="loan_transaction_taken"`);
    `transaction_not_found` (`{transaction_id}`). (3 keys over 4 raises.)
    The module's `PersonalLoanFormError` raises are a plain `Exception`, not a
    `KaletaError`, so they are out of scope.
- **No-period fallbacks preserved.** `gift.not_found`,
  `gift.transaction_not_found`, `personal_loan.*` keep their original
  trailing-period-less English wording byte-identical; the test asserts
  `t(key, **params) == exc.message`.
- **`code` kwargs preserved.** `personal_loan` raises keep their existing
  `code=` values; `message_key`/`params` are added alongside. No behaviour or
  `code` change.
- **i18n placement.** The four sub-blocks are appended at the end of the
  `errors` object (after `transaction`), clustered, so a sibling lane adding
  `errors.irregular_item` (#357) rebases cleanly.
- **View changes.** None — all four are services. The test is
  integration-only and touches no file under `src/kaleta/views/`.
