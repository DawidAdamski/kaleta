---
plan_id: subscriptions-api-write
title: Subscriptions REST API — create, update, delete, cancel
area: api, subscriptions
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#rest-api
---

# Subscriptions REST API — create, update, delete, cancel

## Intent
`/api/v1/subscriptions` is read-only (one `GET /`). Every service method needed for
writes already exists in `SubscriptionService` (`create`, `update`, `delete`, `cancel`,
`reactivate`, `mute_one_cycle`), so an API client (scripts, Claude) has to fall back to
the UI to add a subscription it found in transactions — e.g. yearly ones like Amazon
Prime, BIK, Beeper or Bitwarden. Expose the existing service through the API.

## Scope
- `GET /subscriptions/{id}` → `SubscriptionResponse`, 404 if missing.
- `POST /subscriptions/` (`SubscriptionCreate`) → 201 `SubscriptionResponse`.
- `PUT /subscriptions/{id}` (`SubscriptionUpdate`, partial) → `SubscriptionResponse`, 404.
- `DELETE /subscriptions/{id}` → 204, 404.
- `POST /subscriptions/{id}/cancel` and `/reactivate` → thin wrappers over the service
  (cancel keeps the existing settle-on-due-date behaviour).
- `GET /subscriptions/` gains optional `status` filter (`active|cancelled|muted`).
- Validation: `category_id`, when given, must be the Subscriptions root or its direct child
  (ADR-028) → 422 otherwise. `payee_id` must exist → 422.
- Out of scope: candidate detection / `create_from_candidate` / refile over the API
  (they re-categorise history — separate plan if needed).

## Acceptance criteria
- `uv run pytest tests/integration/test_api_subscriptions.py -q` — covers create → get →
  update (notes, amount, cadence) → cancel → reactivate → delete, the 404s and the
  ADR-028 category 422.
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q` (new routes use
  `get_session`).
- The OpenAPI schema lists every new operation with a summary (asserted in the
  subscriptions API test module).
- `grep -c "KAL-API-010" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`

## Touchpoints
- `src/kaleta/api/v1/subscriptions.py`, `src/kaleta/services/subscription_service.py`
  (read; validation helpers only if missing), `src/kaleta/schemas/subscription.py`
- `tests/integration/test_api_subscriptions.py` (new), `docs/bdd.md` (KAL-API-010)

## Open questions
- Scenario id? Default: KAL-API-010 (KAL-API-009 is taken by the open
  import-transfer-pairs-api PR #425).
- `muted` status filter: does the model have a muted state, or is it derived from
  `mute_one_cycle`? Default: filter on whatever the service exposes. If muted is
  derived, compute it the same way the UI does and record that here.

## Implementation notes
- **Scenario id:** KAL-API-010. KAL-API-009 belongs to import-transfer-pairs-api (PR #425).
- **`muted` filter:** `SubscriptionStatus` has a real `MUTED` value (`mute_one_cycle` sets
  it), so `?status=` is the enum and passes through to `SubscriptionService.list(status=)`.
  Mute itself is not exposed: the plan's scope does not list it.
- **Validation lives in the service** (`SubscriptionService._check_references`), so it
  applies to the UI too. A category outside the Subscriptions tree raises
  `ValidationError(code="invalid_subscription_category")`, and an unknown payee raises
  `code="unknown_payee"`. Both are 422 through the error envelope. On `update`, only a
  reference that *changes* is checked. A row filed outside the tree before ADR-028
  can still be edited (e.g. notes) without first being moved. The UI dialog sends the
  stored `category_id` back on every save, so without this the dialog would refuse the
  edit. The UI dialog only offers tree children, so it never sends a new invalid id.
- **Bug fixed in scope:** `SubscriptionService.create` dropped `notes` from the payload.
  A POST with notes would have silently lost them, so `create` now stores them
  (`test_notes_are_kept_on_create`).
- **Cancel date** is a query parameter (`effective_on`), not a body, matching the service
  signature. A future date only schedules: the row stays active with `cancelled_at`
  set (existing behaviour, `test_future_cancel_only_schedules`).
- The `/api/docs` criterion is now an assertion on `app.openapi()`
  (`test_openapi_gives_every_subscription_operation_a_summary`). The gate runs
  backticked criteria as commands, so a bare `/api/docs` cannot be one.
