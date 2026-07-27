---
plan_id: rules-auto-categorisation
title: Rules — auto-categorisation from payee/description patterns
area: import
effort: medium
status: archived
archived_at: 2026-07-27
roadmap_ref: ../roadmap.md#import
---

# Rules — auto-categorisation from payee/description patterns

## Intent

Recurring merchants should not need recurring clicks: a purchase at
Lidl is groceries by default. Ship a simple core-tier rule engine
(pattern contains → category) with a Rules management page, apply
rules during CSV import, and offer (never silently create) a rule
when the user repeatedly categorises the same merchant the same way.

## Scope

- **Model** `CategorisationRule`: `pattern`, `match_mode` (`contains`
  only), `category_id` FK, `is_active`, `priority`, timestamps,
  optional `user_id`.
- **Schemas** `CategorisationRuleCreate` / `Update` / `Response` plus
  a suggestion DTO for the offer dialog.
- **Service** `RuleService`: CRUD, `match_category_id(payee, description)`
  (case-insensitive contains; try payee then description; first active
  rule by priority desc / id asc wins),
  `suggest_from_corrections` (threshold 4 identical corrections → offer,
  never auto-create).
- **Import** — `ImportService` applies matching rules when building
  `TransactionCreate` rows (overrides default import categories;
  skips internal transfers).
- **Manual wins** — rules run only at import / explicit match time;
  saving a manual category on a transaction never re-applies rules.
- **Views** — Rules page (`/rules`) with add/edit/delete + nav entry;
  transaction edit offers to create a suggested rule after repeated
  corrections.
- **Alembic migration**; **i18n** en + pl; **optional seed** demo rule
  (LIDL → Żywność).
- **Tests** covering KAL-RUL-001–004 with `Covers:` docstrings; retag
  BDD `@automated`.

Out of scope:

- LLM / AI categorisation
- Regex or ML beyond case-insensitive `contains`
- Tag auto-assign
- `ImportRule` filename → account/column mapping (separate plan)

## Acceptance criteria

- `uv run pytest tests/unit/services/test_rule_service.py -q`
- `uv run pytest tests/unit/services/test_import_service.py -q -k rule`
- `uv run pytest tests/e2e/test_rules.py -q`
- `grep -qE "KAL-RUL-001 @automated" docs/bdd.md`
- `grep -qE "KAL-RUL-002 @automated" docs/bdd.md`
- `grep -qE "KAL-RUL-003 @automated" docs/bdd.md`
- `grep -qE "KAL-RUL-004 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

## Touchpoints

- `src/kaleta/models/categorisation_rule.py` — new
- `src/kaleta/schemas/categorisation_rule.py` — new
- `src/kaleta/services/rule_service.py` — new
- `src/kaleta/services/import_service.py` — apply rules on import
- `src/kaleta/views/rules.py` — new page
- `src/kaleta/views/transactions/edit_dialog.py` — suggestion offer
- `src/kaleta/views/layout.py`, `main.py` — nav + register
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `alembic/versions/*_add_categorisation_rules.py`
- `scripts/seed.py` — optional demo rule
- `docs/bdd.md` — retag KAL-RUL
- `tests/unit/services/test_rule_service.py`
- `tests/e2e/test_rules.py`

## Open questions

- Suggestion pattern source: prefer payee name when present, else the
  full description (resolved: yes).
- Multiple matching rules: highest `priority`, then lowest `id`
  (resolved).

## Implementation notes

- Plan file was missing at pickup; created from BDD KAL-RUL-001–004 +
  audit P1.8 notes, then implemented against this scope contract.
- Match semantics: case-insensitive `contains`; payee name tried before
  description. Only `RuleMatchMode.CONTAINS` is accepted.
- Rules apply only in `ImportService.apply_categorisation_rules` (called
  once per import persist). Manual edits never re-run rules — that is
  how KAL-RUL-004 holds without a `category_source` column.
- Suggestions: threshold 4 identical pattern+category corrections;
  `suggest_from_corrections` returns a DTO; the transaction edit dialog
  offers create/dismiss (never silent create). Pattern candidate =
  payee name if present, else trimmed description.
- Spec coverage only scans `tests/e2e` + `tests/integration`, so
  KAL-RUL-003/004 also have integration tests (unit tests alone are
  insufficient for retag).
- Backup round-trip helpers updated to seed `categorisation_rules`
  (new table appears in `Base.metadata.sorted_tables`).

## Implementation

Landed on 2026-07-27.

| SHA | Author | Date | Message |
|---|---|---|---|
| `8c2e17f` | Dawid Adamski | 2026-07-27 | feat: auto-categorisation rules for import and corrections (#32) |

**Files changed:**
- `src/kaleta/models/categorisation_rule.py` (new), `src/kaleta/models/__init__.py`
- `src/kaleta/schemas/categorisation_rule.py` (new)
- `src/kaleta/services/rule_service.py` (new), `src/kaleta/services/import_service.py`
- `src/kaleta/services/__init__.py`
- `src/kaleta/views/rules.py` (new), `src/kaleta/views/layout.py`, `src/kaleta/main.py`
- `src/kaleta/views/transactions/edit_dialog.py`
- `src/kaleta/views/import_view/page.py`
- `src/kaleta/i18n/locales/en.json`, `src/kaleta/i18n/locales/pl.json`
- `alembic/versions/c9d0e1f2a3b4_add_categorisation_rules.py` (new)
- `scripts/seed.py`
- `docs/bdd.md`
- `tests/unit/services/test_rule_service.py` (new), `tests/unit/services/test_import_service.py`
- `tests/e2e/test_rules.py` (new), `tests/e2e/seed_helpers.py`
- `tests/integration/test_categorisation_rules.py` (new), `tests/backup_helpers.py`

**Acceptance criteria run** (step 3b):

| Command | Exit |
|---|---|
| `uv run pytest tests/unit/services/test_rule_service.py -q` | 0 |
| `uv run pytest tests/unit/services/test_import_service.py -q -k rule` | 0 |
| `uv run pytest tests/e2e/test_rules.py -q` | 0 |
| `grep -qE "KAL-RUL-001 @automated" docs/bdd.md` | 0 |
| `grep -qE "KAL-RUL-002 @automated" docs/bdd.md` | 0 |
| `grep -qE "KAL-RUL-003 @automated" docs/bdd.md` | 0 |
| `grep -qE "KAL-RUL-004 @automated" docs/bdd.md` | 0 |
| `uv run python scripts/spec_coverage.py` | 0 |
| `./scripts/verify.sh --e2e` | 0 |
