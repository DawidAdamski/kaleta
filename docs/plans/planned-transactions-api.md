---
plan_id: planned-transactions-api
title: Planned transactions REST API
area: api, planned
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Planned transactions REST API

## Intent
Planned transactions (`/planned`) feed the Payment Calendar together with subscriptions,
but have no API. Standing orders change (e.g. a monthly transfer raised from 2 049,07 to
5 378 zł) and have to be edited by hand in the UI form. `PlannedTransactionService`
already implements `list`, `get`, `create`, `update`, `delete`, `toggle_active`,
`get_occurrences`.

## Scope
- `GET /planned/` (optional `active` filter), `GET /planned/{id}`.
- `POST /planned/` (`PlannedTransactionCreate`, incl. `target_account_id` for
  self-transfers) → 201.
- `PUT /planned/{id}` (`PlannedTransactionUpdate`, partial) → 200; `DELETE /planned/{id}` → 204.
- `POST /planned/{id}/toggle-active`.
- `GET /planned/{id}/occurrences?start=&end=` → dates + amounts in the window.
- Out of scope: posting occurrences (`post_occurrence(s)`, `post_due`) and `link_history`.

## Acceptance criteria
- `uv run pytest tests/integration/test_api_planned.py -q`
- Those tests cover: a CRUD round-trip, monthly occurrences in a 3-month window, a
  self-transfer with `target_account_id`, and the 404s.
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`.
- `grep -c "KAL-API-012" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`

## Touchpoints
- `src/kaleta/api/v1/planned.py` (new) and its registration in `src/kaleta/api/v1/__init__.py`
- `src/kaleta/services/planned_transaction_service.py` (read; validation only if missing)
- `src/kaleta/schemas/planned_transaction.py` (reuse; add an occurrence response if needed)
- `tests/integration/test_api_planned.py` (new), `docs/bdd.md` (KAL-API-012)

## Open questions
- Scenario id? Default: KAL-API-012.
- Path: `/planned` or `/planned-transactions`? Default: `/planned-transactions`, so it reads
  as a resource in the API docs. Record the choice here.
- Occurrence window cap? Default: 366 days, following `MAX_SUGGESTION_SPAN_DAYS` in
  `api/v1/transfer_pairs.py`. `end` is before `start` → 422.
- Unknown `account_id`/`target_account_id`/`category_id` on create: if the service lets
  them reach the database (500 on the foreign key), add a reference check in the
  service (422), the way subscriptions-api-write did.

## Implementation notes
- **Scenario id:** KAL-API-012 (free on `main`).
- **Path:** `/planned-transactions` (the plan default); the router module is
  `src/kaleta/api/v1/planned.py`.
- **Occurrence window:** `start` and `end` are both inclusive, matching
  `get_occurrences`. `end < start` or a span over `MAX_OCCURRENCE_SPAN_DAYS = 366` is 422.
  A paused plan still lists its schedule (`active_only=False`): the endpoint answers "when does
  this plan fall", not "what will the calendar post". The service gained a `planned_id` filter so
  the route does not filter every plan's occurrences itself.
- **Reference checks:** `create` let an unknown `account_id`, `target_account_id`,
  `category_id` or `payee_id` reach the foreign key (500). `_check_references` now refuses them
  with 422 (`unknown_account`, `unknown_category`, `unknown_payee`). `update` checks only an
  `account_id`/`category_id` that changes, so the UI form (which resends every field) is
  unaffected; `PlannedTransactionUpdate` has no `target_account_id`/`payee_id`, and changing that
  schema is out of scope.
- **Null on PUT:** an explicit `null` for a NOT NULL column (`name`, `amount`, `type`,
  `account_id`, `frequency`, `interval`, `start_date`, `is_active`) also reached the database as a
  500. `update` now refuses it with 422 `null_field` before touching the row.
- **Response:** `PlannedTransactionResponse` gained `target_account_id` (the column already
  existed), so a client can see that a plan is a self-transfer. New `PlannedOccurrenceResponse`
  carries date, amount, type, account and category for each occurrence.
- **`list(active=)`:** filtering moved into the service as an optional keyword; existing callers
  pass nothing and see every plan as before.
