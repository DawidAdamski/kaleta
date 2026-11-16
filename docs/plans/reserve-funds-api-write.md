---
plan_id: reserve-funds-api-write
title: Reserve funds and savings goals REST API: get, create, update, archive, delete, contribute, close
area: api, funds
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md
---

# Reserve funds and savings goals REST API: get, create, update, archive, delete, contribute, close

## Intent
`/api/v1/reserve-funds` has a single read-only route, `GET /`. The UI
(`src/kaleta/views/safety_funds.py`) can create, edit, archive, unarchive and delete
emergency, irregular and goal funds, and it can contribute to or close a savings goal
(skarbonka). An API client (scripts, Claude) can do none of this. It cannot open a
"Wakacje 2030" goal, record a transfer into it, or close it and release the money.
`ReserveFundService` already implements every one of these operations, so this plan
exposes them through the API. Two gaps in the service's validation surface once the
input no longer comes from the dialog, and the plan fills them in the service: an
unknown backing account, and a partial update that leaves the fund inconsistent.

Savings goals are reserve funds whose `kind` is `vacation`
(`GOAL_KIND = ReserveFundKind.VACATION` in `reserve_fund_service.py`). There is no
separate goal model or route. A goal is a fund with `kind=vacation` and, optionally,
a `target_date`.

## Scope

### Routes (all in `src/kaleta/api/v1/reserve_funds.py`, every handler on `get_session` from `kaleta.api.deps`)
- `GET /reserve-funds/{fund_id}` → `ReserveFundWithProgress` (from
  `ReserveFundService.get` + `with_progress`). Returns 404 when `get` returns `None`.
  The response carries `current_balance`, `progress_pct`, `months_of_coverage`
  (emergency only), and `months_left` / `monthly_pace` (goal with a `target_date`
  only). Archived funds are returned too.
- `POST /reserve-funds/` (`ReserveFundCreate`) → 201 `ReserveFundResponse` (`create`).
- `PUT /reserve-funds/{fund_id}` (`ReserveFundUpdate`, partial: only the fields in the
  body change, the same as `PUT /subscriptions/{id}`) → `ReserveFundResponse`
  (`update`). Returns 404 when the service returns `None`.
- `DELETE /reserve-funds/{fund_id}` → 204 (`delete`), or 404. Deleting an irregular fund
  also deletes its `IrregularItem` rows through `ondelete="CASCADE"`
  (`models/irregular_item.py`). Transactions are never touched. The route description
  says both.
- `POST /reserve-funds/{fund_id}/archive` and `/unarchive` → `ReserveFundResponse`
  (`archive` / `unarchive`), or 404. These work on any kind, as in the UI. Archiving
  moves no money.
- `POST /reserve-funds/{fund_id}/contribute` (`GoalContribution`) → 200
  `ReserveFundWithProgress`. `ReserveFundService.contribute` returns `None`, so the
  route calls `contribute`, then `get` + `with_progress`, and returns the goal's new
  progress. Errors come from the service (`_goal`, `_move`): 404 for an unknown fund;
  422 when the fund is not a goal, is archived (closed), or has no backing account;
  422 when the source and backing accounts are the same or use different currencies;
  404 for an unknown `from_account_id` (`errors.reserve_fund.account_not_found`).
- `POST /reserve-funds/{fund_id}/close` (`GoalClose`) → 200 `ReserveFundResponse`
  (`close`, which already returns the archived ORM row). With
  `release_to_account_id`, a positive balance is moved there first. Without it, or with
  a zero balance, no transfer is made. Error statuses are the same as for contribute.
- `GET /reserve-funds/` keeps its current contract (`ReserveFundResponse` list,
  `include_archived`). It is not changed.
- Every new operation gets a `summary`, and `responses=` for its 404/422, in the style
  of `src/kaleta/api/v1/subscriptions.py`.

### Response schemas
- No new Pydantic schema is needed. `create`, `update`, `archive`, `unarchive` and
  `close` return the `ReserveFund` ORM row, which goes out through
  `ReserveFundResponse.model_validate`. `with_progress` already returns the
  `ReserveFundWithProgress` schema. `contribute` returns `None`; see above.
- Never return the ORM row itself (AGENTS.md: ORM models stay out of API responses).

### Validation the service is missing (add it in `ReserveFundService`, not the route)
1. **Unknown references on create/update.** `create` and `update` write
   `backing_account_id` / `backing_category_id` straight into the row. An id that does
   not exist fails the FK at commit, and the client gets a 500. Add a private helper,
   `_check_references(backing_account_id, backing_category_id)`, modelled on
   `SubscriptionService._check_references` on branch `plan/subscriptions-api-write`.
   It raises `ValidationError(code="unknown_backing_account",
   message_key="errors.reserve_fund.unknown_backing_account", params={"account_id": …})`,
   and the same with `unknown_backing_category` for a category. Both are 422. On
   `update`, check only a reference the payload *changes*.
2. **Partial update can leave the fund inconsistent.** `ReserveFundUpdate` has no
   validator. `update` checks only multiplier-vs-`target_from_spending`, then
   `setattr`s every field in the body. This lets an API body do three things the
   dialog never sends:
   - set a NOT NULL column to `null` (`name`, `kind`, `target_amount`, `backing_mode`,
     `target_from_spending`). The commit then fails with an IntegrityError, a 500;
   - switch `backing_mode` without the matching reference, which breaks the invariant
     `ReserveFundBase._check_backing_ref` enforces on create. The next
     `ReserveFundResponse.model_validate` of that row then raises, so even
     `GET /reserve-funds/` returns 500;
   - send a non-null `target_date` while the resulting kind is not `vacation`. Today
     the date is silently dropped; `create` refuses the same input with 422.

   Fix: in `update`, merge the stored fields with
   `payload.model_dump(exclude_unset=True)`. When the resulting kind is not
   `GOAL_KIND` and the payload does not set `target_date`, set the merged `target_date`
   to `None`; this keeps today's "kind change drops the date" behaviour. Then validate
   the merged dict through `ReserveFundCreate.model_validate`, and turn a pydantic
   `ValidationError` into `kaleta.exceptions.ValidationError(code="invalid_reserve_fund",
   message_key="errors.reserve_fund.invalid_update")` with the first error's message.
   This replaces the hand-written multiplier check, which the create validator already
   covers. Keep its `message_key` if a test pins it (`test_error_i18n_funds_cohort.py`).
   The UI's update call (`safety_funds.py` `_save`) always sends a full, consistent
   payload, so its behaviour does not change.
- Add the new message keys to `src/kaleta/i18n/locales/en.json` and `pl.json` under
  `errors.reserve_fund`. Keep the diff minimal: only the added keys, no re-indent.

### Not in scope (binding)
- `/reserve-funds/{fund_id}/items` and `/reserve-funds/{fund_id}/plan` (irregular-fund
  items). Those belong to plan `irregular-fund-items-api` (KAL-API-011), whose router
  changes are already in this file on branch `plan/irregular-fund-items-api`. Do not
  add, change or test item routes here. If that branch has merged, rebase onto it and
  keep its routes untouched.
- A progress list (`list_with_progress`) over the API, `emergency_cover` /
  `emergency_cover_months`, `derived_target` / `target_from_monthly` /
  `trailing_monthly_expense` previews, and the static `months_left` /
  `monthly_pace`. These are read-side analysis figures. `GET /{fund_id}` already
  returns pace and coverage for one fund.
- `last_contribution_source` is a dialog convenience. `close` takes an explicit
  `release_to_account_id`.
- Contributions to non-goal funds, envelope-mode balances (`with_progress` returns
  0.00 for `backing_mode=envelope`, as today), and any change to how a balance or
  target is computed.
- Fixing the pre-existing crash when a fund's backing account is deleted
  (`ondelete="SET NULL"` leaves `backing_mode=account` with `backing_account_id=None`,
  which `ReserveFundResponse`'s inherited validator rejects). See Open questions.
- UI changes. No file under `src/kaleta/views/` is touched, so the short
  `verify.sh` gate is enough.

### Scenario (paste into `docs/bdd.md`, Feature: Public API, after KAL-API-011 or the last KAL-API id)

```gherkin
  KAL-API-013 @automated
  Scenario: Run a savings goal end to end through the API
    Given a valid API bearer token
    And accounts "PKO Main" holding 1000.00 PLN, "Konto wakacyjne" holding 0.00 PLN and "Konto EUR" holding 0.00 EUR
    When I POST a fund "Wakacje 2030" of kind vacation with target 6000.00 by 2030-06-01 backed by "Konto wakacyjne" to /api/v1/reserve-funds
    Then the response is 201 with is_archived false
    And GET /api/v1/reserve-funds/{id} shows current_balance 0.00 and progress_pct 0.00
    When I POST a contribution of 500.00 from "PKO Main" dated 2026-11-15 to /api/v1/reserve-funds/{id}/contribute
    Then the response is 200 with current_balance 500.00 and progress_pct 0.08
    And "PKO Main" holds 500.00
    When I PUT name "Wakacje w Grecji 2030" and target_amount 5000.00
    Then the response has that name and target 5000.00, and GET shows progress_pct 0.10
    And a contribution from "Konto EUR" is 422, one from "Konto wakacyjne" to itself is 422
    And a contribution to an emergency fund "Poduszka" is 422
    When I POST /api/v1/reserve-funds/{id}/close releasing to "PKO Main" dated 2026-11-20
    Then the response is 200 with is_archived true
    And "PKO Main" holds 1000.00 and "Konto wakacyjne" holds 0.00
    And GET /api/v1/reserve-funds omits the goal, but include_archived=true lists it
    And a further contribution is 422
    When I POST /api/v1/reserve-funds/{id}/unarchive
    Then is_archived is false and archived_at is null
    When I DELETE /api/v1/reserve-funds/{id}
    Then the response is 204 and GET /api/v1/reserve-funds/{id} is 404
    And a fund backed by account id 999999 is refused with 422
    And a PUT that sets name to null, or a target_date on an emergency fund, is 422
```

Months-left and pace are not asserted: `with_progress` measures them from
`date.today()`, and the verification rule forbids computing the expected value. The
target date of 2030-06-01 keeps the goal in the future for years. That keeps
`months_left` positive and `monthly_pace` non-null, and the test may check both.

## Acceptance criteria
- `uv run pytest tests/integration/test_api_reserve_funds.py -q`
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`
- `uv run pytest tests/integration/test_error_i18n_funds_cohort.py -q`
- `uv run pytest tests/integration/test_analysis_api.py -q`
- `grep -c "KAL-API-013" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- Tests in the new module (each docstring says `Covers: KAL-API-013`), with literals
  from the scenario:
  - `test_goal_round_trip_through_the_api`: create → get (0.00 / 0.00) → contribute
    500.00 (500.00 / 0.08, "PKO Main" 500.00) → put (name, 5000.00, progress 0.10) →
    close with release ("PKO Main" 1000.00, "Konto wakacyjne" 0.00, `is_archived`
    true) → list without and with `include_archived` → unarchive → delete → 404.
  - `test_contribute_refuses_currency_mismatch_self_transfer_and_non_goal`: the three
    422s, plus 422 on a closed goal.
  - `test_close_without_release_moves_no_money`: "Konto wakacyjne" keeps 500.00, and
    the goal is archived.
  - `test_unknown_fund_is_404_on_every_route`: get, put, delete, archive, unarchive,
    contribute and close on id 999999.
  - `test_unknown_backing_account_is_422`: on POST, and on PUT changing
    `backing_account_id`. Error code `unknown_backing_account`.
  - `test_put_cannot_null_a_required_field_or_date_a_non_goal`: `name: null` → 422;
    `target_date: "2030-06-01"` on "Poduszka" → 422; `backing_mode: "envelope"` alone
    → 422. A GET afterwards still returns 200 with the fund unchanged.
  - `test_put_kind_change_drops_the_date`: changing a goal's kind to `emergency` (with
    `emergency_multiplier` 3) clears `target_date` to null. This keeps today's
    behaviour.
  - `test_openapi_gives_every_reserve_fund_operation_a_summary`: an assertion on
    `app.openapi()`, as in the subscriptions module.
- Unit coverage in `tests/unit/services/` for the update-merge validation and
  `_check_references`, if the test-runner agent judges it useful. The integration tests
  above are the gate.

## Touchpoints
- `src/kaleta/api/v1/reserve_funds.py`: the new routes. Shared with the
  irregular-fund-items-api branch; expect a merge conflict in the imports only.
- `src/kaleta/services/reserve_fund_service.py`: `_check_references`, the
  merged-state validation in `update`, and the reference check in `create`.
- `src/kaleta/schemas/reserve_fund.py`: read only; reuse `ReserveFundCreate`,
  `ReserveFundUpdate`, `ReserveFundResponse`, `ReserveFundWithProgress`,
  `GoalContribution`, `GoalClose`.
- `src/kaleta/i18n/locales/en.json`, `src/kaleta/i18n/locales/pl.json`: new keys
  `errors.reserve_fund.unknown_backing_account`, `unknown_backing_category`,
  `invalid_update`.
- `tests/integration/test_api_reserve_funds.py` (new), and
  `tests/integration/test_error_i18n_funds_cohort.py` if it enumerates funds-cohort
  keys.
- `docs/bdd.md`: KAL-API-013.
- Reference only: `src/kaleta/api/v1/subscriptions.py` and
  `SubscriptionService._check_references` on branch `plan/subscriptions-api-write`,
  `src/kaleta/api/v1/payees.py`, and `tests/integration/conftest.py` (`api_client`,
  `create_account`).

## Open questions
- **Contribute's response?** Default: `ReserveFundWithProgress` from `get` +
  `with_progress` after the transfer. Do not change `contribute`'s `None` return.
  The view ignores it, and a return change is not needed.
- **Unknown `from_account_id` / `release_to_account_id`: 404 or 422?** Default: keep
  the service's `NotFoundError` (404, `errors.reserve_fund.account_not_found`). Do not
  retype an existing domain error the UI also relies on. Document the 404 in the route's
  `responses`.
- **Should `create` reject `backing_mode=envelope`, which the UI does not offer?**
  Default: no. The schema allows it, so accept it and check that the category exists.
  The balance stays 0.00 as today.
- **Should the transfers that contribute and close create carry the fund's name as
  their description when none is given?** Default: no. Pass `description` through
  unchanged (empty string by default), as the UI does.
- **The crash after a backing account is deleted** (see Not in scope): fix it here?
  Default: no. Add one line to `docs/plans/chores.md` in this branch, e.g. "A reserve
  fund whose backing account was deleted (SET NULL) fails `ReserveFundResponse`
  validation, so `GET /reserve-funds` returns 500. Decide: block account delete, or relax
  the response validator." Do not fix it.
- **Progress list route (`GET /reserve-funds/progress`)?** Default: not added (see
  Not in scope). If it is ever added, register it before `/{fund_id}`, because
  Starlette would otherwise match `progress` as a `fund_id` and return 422.
- **Scenario id?** Default: KAL-API-013. KAL-API-010 is subscriptions, 011 is
  irregular-fund-items-api, and 012 is reserved by another open plan.

## Implementation notes
- **Scenario id:** KAL-API-013 (free on `main`; 010–012 merged).
- **Irregular items:** #428 is merged, so this branch starts from `main` with the item routes
  already in `reserve_funds.py`. They are untouched; the OpenAPI test counts 14 operations
  under `/reserve-funds` (9 from this plan + 5 item routes).
- **Update validation:** `update` merges the stored fields with the body and validates the
  result through `ReserveFundCreate`; a pydantic error becomes 422
  `invalid_reserve_fund` (`errors.reserve_fund.invalid_update`, the first error as
  `{reason}`). When the resulting kind is not a goal and the body does not set
  `target_date`, the merged date is cleared first, so a kind change still drops the date
  (tested). The hand-written multiplier check is **kept** in front of it: the cohort test
  pins `errors.reserve_fund.multiplier_required_for_spending_target`, and the dialog's toast
  keeps its specific wording.
- **Reference checks:** `_check_references` refuses an unknown backing account / category
  (422 `unknown_backing_account` / `unknown_backing_category`, with i18n keys in both
  locales). `update` checks only a reference the body changes. The three new keys are
  added to the funds-cohort list in `test_error_i18n_funds_cohort.py`.
- **Contribute response:** `contribute` still returns `None`; the route re-reads the fund
  and returns `with_progress`. Unknown `from_account_id` / `release_to_account_id` stay 404
  (`account_not_found`) and are documented in `responses`.
- **Envelope funds:** accepted on create as the schema allows; only the category's
  existence is checked.
- **Months left / pace:** only asserted as positive / non-null (they depend on today).
- **Deleted backing account crash:** not fixed; logged in `docs/plans/chores.md`.
