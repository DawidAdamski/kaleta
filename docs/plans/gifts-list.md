---
plan_id: gifts-list
title: Gifts — maintain the gift list (person, occasion, amount)
area: views (gifts)
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md
---

# Gifts — maintain the gift list (person, occasion, amount)

## Intent
Dogfooding #21 / GitHub #11, #21. A new "Gifts" page so the user can plan
gifts per person and occasion for the year: add entries like
"Mum — birthday — 200.00", see them grouped by the person they are for, and
read a single yearly total. This is slice 1 of the Gift Planning feature
(BDD `KAL-GFT-001`). It stands on its own — a usable gift list — and lays the
per-row model that the later slices build on.

## Scope
Slice 1 = `KAL-GFT-001` only: maintain the gift list.

- **New per-row model `Gift`** (`src/kaleta/models/gift.py`): `person` and
  `occasion` as `EncryptedText` (user text), `amount` as `Numeric(15,2)`,
  `TimestampMixin` + `UserOwnedMixin` (matching `IrregularItem`). Per-row (one
  row per person+occasion), not a JSON blob, so the later slices
  (`KAL-GFT-002` fund feed, `KAL-GFT-003` link a transaction / mark bought)
  attach to an individual gift. Registered in `models/__init__.py`.
- **Alembic migration** creating `gifts` (family schema, `alembic/versions/`,
  `down_revision` = current head). EncryptedText columns → `sa.LargeBinary()`;
  index the `user_id` FK; timestamps with a server default.
- **Schemas** (`src/kaleta/schemas/gift.py`): `GiftBase` / `GiftCreate` /
  `GiftUpdate` / `GiftResponse` (`from_attributes=True`), plus a grouped
  summary schema `GiftPersonGroup` + `GiftsSummary` carrying the per-person
  groups and the yearly total.
- **Service** (`src/kaleta/services/gift_service.py`): `create`, `list`,
  `update`, `delete`, and a `summary()` that groups rows **by person in
  Python** (person is encrypted, so grouping cannot be done in SQL) and sums
  amounts with `Decimal` into the yearly total. Registered in
  `services/__init__.py`.
- **View** (`src/kaleta/views/gifts.py`, single file modelled on
  `safety_funds.py`): a page at `/wizard/gifts` listing gifts grouped under
  each person, the yearly total, and an Add dialog (person, occasion, amount).
  Registered in `main.py` `_register_views()`; nav entry in `layout.py`
  `NAV_GROUPS` under `nav.group_plans`.
- **i18n**: a `gifts` block in `en.json` + `pl.json` (same keys), and
  `nav.gifts` in both.
- **Seeder** (`src/kaleta/seeders/gifts.py`): a few Polish example gifts,
  idempotent, registered in `seeders/__init__.py`.
- **Tests**: unit tests for `GiftService` (`tests/unit/services/`), and an e2e
  `tests/e2e/test_gifts.py` covering `KAL-GFT-001` with a `seed_gift`
  service-layer helper in `tests/e2e/seed_helpers.py`.
- **BDD**: retag `KAL-GFT-001` `@planned` → `@automated`.

**Not in scope (binding):**
- `KAL-GFT-002` (feed the Irregular Expenses Fund) and `KAL-GFT-003` (link a
  transaction, mark bought with actual cost) — later slices. No fund wiring,
  no transaction link, no bought/actual-cost fields, no "divide by 10" maths
  here.
- No REST `api/v1/gifts.py` route (the e2e helper seeds through the service).
- No category link on a gift yet.

## Acceptance criteria
- `uv run pytest tests/unit/services/test_gift_service.py -q`
- `uv run pytest tests/e2e/test_gifts.py -q`
- `grep -q "KAL-GFT-001 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

Fail-on-old: `tests/e2e/test_gifts.py` (KAL-GFT-001) cannot pass before this
slice — there is no Gifts page, model or service — so it is new behaviour, not
a regression guard over existing code. The unit test asserts the grouping and
the yearly total against the BDD literals (200.00 + 150.00 → 350.00 under
"Mum").

## Touchpoints
- `src/kaleta/models/gift.py`
- `src/kaleta/models/__init__.py`
- `alembic/versions/<hexid>_add_gifts.py`
- `src/kaleta/schemas/gift.py`
- `src/kaleta/services/gift_service.py`
- `src/kaleta/services/__init__.py`
- `src/kaleta/views/gifts.py`
- `src/kaleta/main.py`
- `src/kaleta/views/layout.py`
- `src/kaleta/i18n/locales/en.json`
- `src/kaleta/i18n/locales/pl.json`
- `src/kaleta/seeders/gifts.py`
- `src/kaleta/seeders/__init__.py`
- `tests/unit/services/test_gift_service.py`
- `tests/e2e/test_gifts.py`
- `tests/e2e/seed_helpers.py`
- `docs/bdd.md`

## Open questions
- None blocking. Field names: `person` + `occasion` (two columns), grouping by
  `person`. Yearly total = plain sum of all gift amounts (no proration in
  slice 1).

## Implementation notes
- Migration parity: not checked via standalone `uv run alembic check` (not a
  project CI gate; it needs the tenant schema at head and is finicky to invoke
  with `-x tenant_schema=`). Parity is instead enforced by the suite: the
  integration/e2e family schema is provisioned through the real migrations
  (`AlembicSchemaProvisioner`, tests/suite_family.py), and unit tests build the
  same schema from `Base.metadata.create_all` — two independent builds that
  diverge loudly if the migration and the model disagree. `./scripts/verify.sh
  --e2e` runs both, so the `gifts` migration is exercised there.
