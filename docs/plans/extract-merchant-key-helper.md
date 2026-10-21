---
plan_id: extract-merchant-key-helper
title: Extract merchant_key_from_description into a shared helper module
area: services
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Extract merchant_key_from_description into a shared helper module

## Intent
`merchant_key_from_description` is the detector's description→merchant-key
normaliser. It lives in `subscription_service`, but the radar
(`unplanned_radar_service`) and `PlannedPriceDriftService` import it from
there, and `subscription_service` itself now imports
`PlannedTransactionService`. Nothing is circular yet, but the services are
coupled through this helper. Moving it to a small, dependency-free helper
module decouples them.

## Scope
Covers:
- Move `merchant_key_from_description` and its private dependency
  (`_MERCHANT_KEY_MAX_LEN` constant + the whitespace regex use) into a new
  module `kaleta/services/merchant_key.py`.
- Update `subscription_service`, `unplanned_radar_service` and
  `planned_price_drift_service` to import it from the new module.
- Drop the now-unused `import re` from `subscription_service`.
- Add one tiny unit test pinning a couple of literal description→key mappings.

Does NOT cover:
- Any logic change — pure move, behaviour identical.
- Models, migrations, schemas.
- Moving `suggest_purpose_index` or `_MERCHANT_PURPOSE_HINTS` (they stay in
  `subscription_service` and call the helper via the new import).

## Acceptance criteria
- `uv run lint-imports` (4 kept, 0 broken)
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run pytest tests/unit/services/test_merchant_key.py -q`
- `grep -q "from kaleta.services.merchant_key import merchant_key_from_description" src/kaleta/services/subscription_service.py`

## Touchpoints
- `src/kaleta/services/merchant_key.py` (new)
- `src/kaleta/services/subscription_service.py`
- `src/kaleta/services/unplanned_radar_service.py`
- `src/kaleta/services/planned_price_drift_service.py`
- `tests/unit/services/test_merchant_key.py` (new)

## Implementation notes
- Chosen location: `kaleta/services/merchant_key.py`, matching the repo's
  existing convention of small loose-function helper modules that live
  inside the services layer (`text_order.py`, `loan_links.py`,
  `day_totals.py`, `attribution.py`). Same-layer siblings may import it, so
  the import-linter `layers` contract stays satisfied with no new ignore.
