---
plan_id: irregular-fund-items-api
title: Irregular fund items REST API
area: api, funds
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Irregular fund items REST API

## Intent
The irregular-expenses fund (`/wizard/safety-funds/{id}`) is driven by `IrregularItem`
rows (name, yearly amount, due month, category). They can only be edited in the UI and
`/reserve-funds/` does not even return them, so a client cannot check whether a yearly
cost (Disney, Amazon Prime, BIK, insurance…) is already covered by the fund, nor keep
the list in sync with the budget plan. `IrregularItemService` already implements
`items`, `plan`, `create`, `update`, `delete`.

## Scope
- `GET /reserve-funds/{fund_id}/items` → `list[IrregularItemResponse]`
  (includes computed `monthly_contribution`).
- `GET /reserve-funds/{fund_id}/plan` → `IrregularFundPlan` (items + derived lines such as
  gifts + monthly total).
- `POST /reserve-funds/{fund_id}/items` (`IrregularItemCreate`) → 201.
- `PUT /reserve-funds/{fund_id}/items/{item_id}` (`IrregularItemUpdate`, partial) → 200.
- `DELETE /reserve-funds/{fund_id}/items/{item_id}` → 204.
- 404 when the fund does not exist or the item belongs to another fund; 422 when the fund
  is not `kind=irregular`.
- Out of scope: funding plan creation, `record_payment`, `link_payment`, history.

## Acceptance criteria
- `uv run pytest tests/integration/test_api_irregular_items.py -q`
- Those tests cover: a CRUD round-trip, the plan total equal to the sum of
  `monthly_contribution` plus derived lines, wrong-fund 404, and non-irregular fund 422.
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`.
- `grep -c "KAL-API-011" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`

## Touchpoints
- `src/kaleta/api/v1/reserve_funds.py` (new routes beside the existing list)
- `src/kaleta/services/irregular_item_service.py` (fund-scoped update/delete)
- `src/kaleta/schemas/irregular_item.py` (read; existing schemas are reused)
- `tests/integration/test_api_irregular_items.py` (new), `docs/bdd.md` (KAL-API-011)

## Open questions
- Scenario id? Default: KAL-API-011 (009 is transfer pairs, 010 is subscriptions).
- `update`/`delete` take only `item_id` today, so an item under another fund's path
  would be changed. Default: give both an optional `fund_id` that, when given,
  must match (else NotFoundError). The UI keeps calling them without it.

## Implementation notes
