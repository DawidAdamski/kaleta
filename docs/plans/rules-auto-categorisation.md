---
plan_id: rules-auto-categorisation
title: Rules — core-tier auto-categorisation engine
area: rules / import
effort: large
status: draft
roadmap_ref: ../roadmap.md#cross-cutting-principles
source: audit-production-readiness.md#8-no-rule-based-auto-categorisation
---

# Rules — core-tier auto-categorisation engine

## Intent

Every import session currently requires manual categorisation — the
largest daily time cost. The AI tier is the roadmap answer; this
plan ships a **simple core-tier rule engine** (payee/description
contains X → category Y, with rules suggested from past
corrections) as the natural precursor. Implements existing BDD
`KAL-RUL-001`–`004` (still `@planned`).

## Scope

- **Model** `CategorisationRule` (name TBD): match field
  (description / payee), operator (`contains`, case-insensitive),
  pattern string, target `category_id`, priority / created_at,
  enabled flag
- **Service** `RuleService`: CRUD; `apply(transaction | import row)
  → category_id | None`; suggestion helper from repeated manual
  corrections (threshold: 3 same description/payee → category, per
  `KAL-RUL-003`)
- **Rules page** (view + nav): list, add, edit, delete, toggle
  (`KAL-RUL-001`)
- **Import path**: after parse, apply matching rules before
  preview/commit; pre-fill category (`KAL-RUL-002`)
- **Manual wins**: user-set category is not overwritten by later
  rule re-application (`KAL-RUL-004`)
- Alembic migration; seed optional demo rule; i18n
- Unit + import integration tests; retag `KAL-RUL-*` to
  `@automated` when covered

Distinct from import **filename mapping** rules in
[`import-per-file-mapping-memory.md`](import-per-file-mapping-memory.md)
(`ImportRule` = columns/account, not category).

### Not in scope

- LLM / paid AI insights (`KAL-AIN-*`)
- Regex-heavy or ML classifiers beyond contains-match
- Auto-creating rules without user confirmation on suggest
  (`KAL-RUL-003` is an **offer**, not silent create)
- Tag auto-assignment (category only in v1)

## Acceptance criteria

- `uv run pytest tests/unit/services/test_rule_service.py -q`
- `grep -E 'KAL-RUL-00[1-4]' docs/bdd.md | grep -q .`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `[manual]` Rules page reachable from nav; create LIDL→Groceries;
  import CSV with LIDL row shows Groceries pre-selected.

## Touchpoints

- `src/kaleta/models/categorisation_rule.py` (new)
- `src/kaleta/schemas/` — rule create/update/response
- `src/kaleta/services/rule_service.py` (new)
- `src/kaleta/services/import_service.py` — apply on import
- `src/kaleta/views/rules.py` (new) + `main.py` route + layout nav
- `src/kaleta/i18n/locales/{en,pl}.json`
- `alembic/versions/` — migration
- `scripts/seed.py` — optional demo rule
- `docs/bdd.md` — retag `KAL-RUL-001`–`004`
- `tests/unit/services/test_rule_service.py`
- `tests/e2e/` — rule create + import apply

## Open questions

1. Match on payee name vs description substring first when both
   exist? Default: try payee, then description.
2. Where in nav — under Transactions vs Settings? Default: own
   **Rules** nav entry next to Categories (matches BDD "Rules
   page").

## Implementation notes

_Filled in as work progresses._

Confirmed greenfield in `audit-planned-vs-code.md` (KAL-RUL).
Source finding: `audit-production-readiness` P1.8. One plan = one
branch = one PR.
