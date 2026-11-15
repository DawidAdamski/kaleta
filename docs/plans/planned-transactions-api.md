---
plan_id: planned-transactions-api
title: Planned transactions REST API
area: api, planned
effort: small
status: draft
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
