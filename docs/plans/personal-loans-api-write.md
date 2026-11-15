---
plan_id: personal-loans-api-write
title: Personal loans REST API: counterparties, loans, repayments, totals
area: api, personal-loans
effort: medium
status: draft
roadmap_ref: ../roadmap.md
---

# Personal loans REST API: counterparties, loans, repayments, totals

## Intent
`/api/v1/personal-loans` only has `GET /`, and that returns loans without
repayments or a balance. `PersonalLoanService` already does the rest:
counterparty CRUD, `create_loan`, `update_loan`, `delete_loan`, `record_repayment`,
`delete_repayment`, `list_link_candidates` and `totals`. None of it is exposed, so an
API client (a script, Claude) that spots "przelew dla Marka 400 zł" in the ledger
cannot record the loan or its repayment without going through the UI. Expose the service,
and close the validation gaps that would show up as 500s once arbitrary
JSON can reach it.

## Scope

### Endpoints (all in `src/kaleta/api/v1/personal_loans.py`, all with `summary=`)
Static paths (`/counterparties`, `/totals`, `/link-candidates`) are declared **before**
`/{loan_id}`. Otherwise FastAPI matches `/{loan_id}` first and answers 422.

Counterparties:
- `GET /personal-loans/counterparties` → `list[CounterpartyResponse]` (`list_counterparties`, name order).
- `POST /personal-loans/counterparties` (`CounterpartyCreate`) → 201 `CounterpartyResponse`
  (`create_counterparty`). A duplicate name → 409.
- `GET /personal-loans/counterparties/{cp_id}` → `CounterpartyResponse` (`get_counterparty`), 404.
- `PUT /personal-loans/counterparties/{cp_id}` (`CounterpartyUpdate`, partial) →
  `CounterpartyResponse` (`update_counterparty`, `None` → 404). A rename onto a taken name → 409.

Loans:
- `GET /personal-loans/` gains an optional `status` query (`LoanStatus`:
  `outstanding|settled`), passed to `list_loans(status=)`. The response model becomes
  `list[PersonalLoanWithRepayments]`. That model is a superset of `PersonalLoanResponse`, so the change only
  adds fields, and `test_list_personal_loans_empty` in `tests/integration/test_analysis_api.py` stays green.
- `GET /personal-loans/{loan_id}` → `PersonalLoanWithRepayments` (`get_loan`), 404.
- `POST /personal-loans/` (`PersonalLoanCreate`) → 201 `PersonalLoanWithRepayments` (`create_loan`).
- `PUT /personal-loans/{loan_id}` (`PersonalLoanUpdate`, partial) → `PersonalLoanWithRepayments`
  (`update_loan`, `None` → 404). `"transaction_id": null` unlinks the principal transaction.
  `"status": "settled"` closes the loan by hand (forgive the rest), and `"outstanding"` reopens it.
- `DELETE /personal-loans/{loan_id}` → 204 (`delete_loan`, `False` → 404). Repayments go with
  it. Linked and mirrored transactions stay in the ledger (existing behaviour, see the docstring).

Repayments:
- `POST /personal-loans/{loan_id}/repayments` (`RepaymentCreate`) → 201 `RepaymentResponse`
  (`record_repayment`, `None` → 404). Three modes, as the service has them:
  plain (no link), `link_transaction_id` (point at an existing ledger transaction; it must
  exist → else 404 via `NotFoundError`, and must not be linked to any loan or repayment →
  409 `loan_transaction_taken`), or `link_account_id` (+ optional `link_category_id`) to
  mirror the repayment as a new transaction. That transaction is INCOME for an `outgoing` loan
  and EXPENSE for an `incoming` one, with the description `Personal loan repayment: <name>`.
  Sending both `link_transaction_id` and `link_account_id` gives 422 `repayment_link_ambiguous`.
- `DELETE /personal-loans/{loan_id}/repayments/{repayment_id}` → 204, 404 when the repayment
  does not exist **or belongs to another loan**. A linked or mirrored transaction stays.

Read-only helpers:
- `GET /personal-loans/totals` → `LoanTotals` (`totals`).
- `GET /personal-loans/link-candidates?limit=200` → `list[LoanLinkCandidate]`
  (`list_link_candidates(limit=)`, `limit` bounded 1..500). Worth exposing: it is the only
  query that already drops internal transfers and transactions linked to a loan, which
  is exactly what a client needs to pick `transaction_id` / `link_transaction_id`. `include_ids`
  is not exposed (it exists for the UI edit dialog).

### Business rules (reused from KAL-DBT-001..005 and the service, not new)
- **Loan closes automatically.** `record_repayment` sets `status=settled` and stamps
  `settled_at` when `principal - sum(repayments) <= 0`. Otherwise it sets `outstanding`
  and clears `settled_at`. `delete_repayment` re-evaluates the same way.
- **Overpayment is allowed.** The service has no cap. An overpaid loan is `settled` and
  `remaining` goes negative (e.g. `-50.00`). The API keeps that (see Open questions).
- **A linked transaction is loan money**, not income or spending (KAL-DBT-004/005, via
  `loan_linked_transaction_ids`). One transaction links at most one principal or repayment
  (unique constraints plus `_check_linkable`, race → `_commit_link` → 409).
- Totals sum `remaining` of outstanding loans by direction: `outgoing` →
  `they_owe_you`, `incoming` → `you_owe`.

### Response schemas
- No service method returns a dataclass. `RepaymentResponse`, `LoanTotals` and
  `LoanLinkCandidate` are already Pydantic and come back as they are. ORM rows go through
  `CounterpartyResponse.model_validate` / `PersonalLoanWithRepayments`.
- `PersonalLoanWithRepayments` (in `src/kaleta/schemas/personal_loan.py`, used nowhere yet)
  has the computed fields `counterparty_name`, `repaid_total` and `remaining`, which plain
  `model_validate(loan)` cannot fill. Add one private router helper `_loan_out(loan)` that builds
  it from the ORM row, with `remaining` from `compute_remaining` in
  `kaleta.services.personal_loan_service`. The `repaid_total` sum is quantized to 0.01. Do not import services
  into `kaleta.schemas` (import-linter forbids it).

### Validation missing in the service (fix there, so the UI benefits too)
Each of these reaches the database today and comes back as an unhandled `IntegrityError`, which is a 500:
1. `create_counterparty` / `update_counterparty`: duplicate name (unique `name_bidx`).
   Check `get_counterparty_by_name` first (on update only when the name changes) →
   `ConflictError(code="counterparty_name_taken")` → 409.
2. `create_loan` / `update_loan`: unknown `counterparty_id` (FK). Check with
   `get_counterparty` (on update only when it changes) →
   `ValidationError(code="unknown_counterparty")` → 422.
3. `record_repayment`: unknown `link_account_id` / `link_category_id` (FK on the mirrored
   transaction). Check with `session.get(Account, …)` / `session.get(Category, …)` before the
   flush → `ValidationError(code="unknown_account" | "unknown_category")` → 422.
4. `update_loan` with `status`: today it sets `status` but leaves `settled_at` alone, so a
   hand-settled loan has no settle date and a reopened one keeps a stale one. When `status`
   changes to `settled`, stamp `settled_at = now(UTC)`. When it changes to `outstanding`,
   clear it.
5. `delete_repayment(repayment_id)` has no loan scope. Add a keyword
   `loan_id: int | None = None`. When it is given and differs from the repayment's `loan_id`, return
   `False` (→ 404). The UI call `delete_repayment(rep_id)` is unchanged.

Each new error gets `message_key="errors.personal_loan.<…>"` in the style of the existing
ones, plus the keys in `src/kaleta/i18n/locales/en.json` / `pl.json` (minimal diff, only the added keys).

### Scenario (paste into `docs/bdd.md`, Feature: Public API, after KAL-API-009)

```gherkin
  KAL-API-018 @automated
  Scenario: Track money lent to a person through the API
    Given a valid API bearer token
    And an account "mKonto" holding an income of 250.00 PLN dated 2026-11-10
    When I POST the counterparty "Marek Nowak" to /api/v1/personal-loans/counterparties
    Then the response is 201
    And POSTing "Marek Nowak" again is refused with 409
    When I POST a loan of 400.00 PLN, direction outgoing, to "Marek Nowak" opened on 2026-11-01
    Then the response is 201 with status outstanding and remaining 400.00
    When I POST a 250.00 repayment dated 2026-11-10 linked to the 250.00 income on "mKonto"
    Then GET of the loan shows repaid_total 250.00, remaining 150.00, status outstanding
    And linking that same income to a second repayment is refused with 409
    When I POST a 200.00 repayment dated 2026-11-20 mirrored to account "mKonto"
    Then "mKonto" holds a 200.00 income "Personal loan repayment: Marek Nowak" dated 2026-11-20
    And the loan is settled with remaining -50.00 and a settled_at stamp
    When I POST a loan of 150.00 PLN, direction incoming, from "Anna Kowalska" opened on 2026-11-05
    Then GET /api/v1/personal-loans/totals shows they_owe_you 0.00, you_owe 150.00, outstanding_count 1, settled_count 1
    When I DELETE the 200.00 repayment
    Then the "Marek Nowak" loan is outstanding again with remaining 150.00 and no settled_at
    And the 200.00 income stays on "mKonto"
    When I PUT status settled on the "Anna Kowalska" loan
    Then it is settled with a settled_at stamp
    And a loan naming an unknown counterparty is refused with 422
    And a repayment giving both link_transaction_id and link_account_id is refused with 422
    And a repayment mirrored to an unknown account is refused with 422
    And deleting a repayment through another loan's URL is 404
    When I DELETE the "Marek Nowak" loan
    Then the response is 204, its repayments are gone and the 250.00 and 200.00 incomes stay on "mKonto"
```

### Out of scope
- `DELETE /personal-loans/counterparties/{id}`. There is no service method, and the model
  cascades a counterparty delete to all its loans. That needs its own decision.
- A `counterparty_name` shortcut on loan create (the UI's `upsert_counterparty` flow). Clients
  create or look up the counterparty first.
- Editing a repayment (no `update_repayment` in the service). Delete and re-post instead.
- Deleting the mirrored transaction together with its repayment or loan.
- Currency checks: a repayment has no currency, a mirrored transaction may land on a
  foreign-currency account, and `totals` adds PLN and EUR loans together. That is existing
  behaviour. Note it in `docs/plans/chores.md` if it bites, and do not fix it here.
- Checking that a linked transaction's amount or direction matches the repayment. The UI does not check it either.
- Re-evaluating `status` when `update_loan` changes `principal`.
- Any view change. The UI keeps its own calls (only `delete_repayment` gains an optional kwarg).

## Acceptance criteria
- `uv run pytest tests/integration/test_api_personal_loans.py -q`
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`
- `uv run pytest tests/integration/test_analysis_api.py -q`
- `uv run pytest tests/unit/services/test_personal_loan_service.py tests/unit/services/test_loan_ledger_link.py -q`
- `grep -c "KAL-API-018" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- Tests in the new module (each docstring carries `Covers: KAL-API-018`, expected values are the
  scenario's literals): `test_counterparty_create_get_update_and_duplicate_409`,
  `test_loan_lifecycle_link_mirror_overpay_settle` (the main scenario walk: 400.00 → link
  250.00 → mirror 200.00 → settled at -50.00), `test_totals_by_direction`,
  `test_delete_repayment_reopens_loan_and_keeps_transaction`,
  `test_put_status_settled_stamps_settled_at`, `test_same_transaction_linked_twice_is_409`,
  `test_unknown_counterparty_and_unknown_account_are_422`,
  `test_ambiguous_repayment_link_is_422`, `test_repayment_of_another_loan_is_404`,
  `test_delete_loan_keeps_linked_transactions`, `test_list_filters_by_status`,
  `test_link_candidates_skip_linked_and_internal_transfers`, and
  `test_openapi_gives_every_personal_loan_operation_a_summary` (asserts on `app.openapi()`).
- Service-level tests for gaps 1, 4 and 5 go in `tests/unit/services/test_personal_loan_service.py`
  (duplicate counterparty → `ConflictError`, status change stamps or clears `settled_at`,
  `delete_repayment(loan_id=…)` mismatch returns `False`).
- Verification: the short `./scripts/verify.sh` gate passes (no view change).

## Touchpoints
- `src/kaleta/api/v1/personal_loans.py`: the new routes and the `_loan_out` helper.
- `src/kaleta/services/personal_loan_service.py`: validation gaps 1–5.
- `src/kaleta/schemas/personal_loan.py`: read only. `PersonalLoanWithRepayments` already inherits
  `from_attributes` from `PersonalLoanResponse`.
- `src/kaleta/i18n/locales/en.json`, `src/kaleta/i18n/locales/pl.json`: new `errors.personal_loan.*` keys.
- `tests/integration/test_api_personal_loans.py` (new), `tests/unit/services/test_personal_loan_service.py`.
- `docs/bdd.md`: KAL-API-018.

## Open questions
- **Overpayment: refuse or allow?** Default: allow, as the service does today. The loan
  settles and `remaining` goes negative. Friends round up, and refusing would break the UI's
  existing behaviour. The scenario pins `-50.00`.
- **Response to `POST …/repayments`: the repayment or the whole loan?** Default:
  `RepaymentResponse`, which is what `record_repayment` returns. The client GETs the loan for the balance.
- **Unknown `link_transaction_id`: 404 or 422?** Default: 404, as `_check_linkable` raises
  `NotFoundError` today and KAL-API-009 also answers an unknown id with 404. Unknown
  `counterparty_id` / `link_account_id` / `link_category_id` are new checks and use 422, as
  subscriptions do for an unknown payee (KAL-API-010).
- **`link_category_id` without `link_account_id`?** Default: ignored, as today. The UI's
  `parse_repayment_form` can send a category while the account is "none", so rejecting it would
  break the dialog.
- **Expose `link-candidates`?** Default: yes, read-only, `limit` only (reasoning in Scope).
- **List response model change?** Default: `GET /` returns `PersonalLoanWithRepayments`. The change
  only adds fields, and the client gets balances without N+1 GETs. `list_loans` already
  eager-loads repayments and counterparty.
- **Scenario id?** Default: KAL-API-018 (010 is subscriptions, 011 is irregular fund items, and the
  ids in between are reserved by other drafts).

## Implementation notes
