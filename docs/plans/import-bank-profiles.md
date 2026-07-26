---
plan_id: import-bank-profiles
title: Import — bank profiles from real dogfood exports
area: import
effort: medium
status: draft
roadmap_ref: ../roadmap.md#import
source: audit-production-readiness.md#7-import-profiles-generic-csv--mbank-only
---

# Import — bank profiles from real dogfood exports

## Intent

`import_service` auto-detects mBank and falls back to a generic
header-alias parser. Other banks used daily (seed suggests PKO,
Revolut) depend on the generic parser coping with each export's
columns, dates, and encoding. During the first month of dogfooding,
collect **one real export per bank actually used**; for each format
the generic parser mishandles, add a profile (or alias entries) plus
a fixture test. Driven by real files — not speculation.

## Scope

- Process:
  1. Save anonymized sample exports under
     `tests/e2e/fixtures/` or `tests/fixtures/import/`
  2. Attempt import with `generic` / `mbank`; document failure mode
  3. Add profile preprocessor and/or header aliases + date/encoding
     handling in `import_service`
  4. Register profile in
     `views/import_view/constants.py` and i18n labels
  5. Unit test with the fixture; e2e smoke if UI profile select
     changes
- Extend detection when profile=`generic` only when signatures are
  unambiguous (same pattern as mBank)
- Keep changes minimal: prefer alias / date-format extensions over
  a new preprocessor class unless the format needs it

Distinct from
[`import-per-file-mapping-memory.md`](import-per-file-mapping-memory.md)
(filename → column mapping memory / `ImportRule`). This plan is
**parser profiles**; that plan is **remembered mappings**.

### Not in scope

- Speculative profiles without a real fixture in-repo
- Open Banking / API bank sync
- Per-file mapping memory UI (separate plan)
- Auto-categorisation rules (see `rules-auto-categorisation`)

## Acceptance criteria

- `test -f tests/e2e/fixtures/mbank_transfer.csv` (existing baseline)
- `uv run pytest tests/unit/services/test_import_service.py -q`
- `grep -E 'KAL-CSV-' docs/bdd.md | grep -q .`
- `uv run python scripts/spec_coverage.py`
- `[manual]` For each new bank profile: real (anonymized) fixture
  imported end-to-end with correct dates, amounts, and currency;
  BDD scenario added (`KAL-CSV-00N`) tagged `@automated` when
  covered by a test.

## Touchpoints

- `src/kaleta/services/import_service.py`
- `src/kaleta/views/import_view/constants.py`
- `src/kaleta/i18n/locales/{en,pl}.json`
- `tests/unit/services/test_import_service.py`
- `tests/e2e/fixtures/` — anonymized bank CSVs
- `docs/bdd.md` — new `KAL-CSV-*` per bank when automated

## Open questions

1. **Which banks first?** Unknown until dogfood exports land —
   candidates from seed (PKO, Revolut) are **not** committed
   profiles until a fixture proves need.
2. **PII scrubbing standard** for fixtures — strip account numbers
   / names; keep amount/date/description shape.

## Implementation notes

_Filled in as work progresses. Log each bank + fixture path here
as dogfood files arrive._

Source finding: `audit-production-readiness` P1.7. One plan = one
branch = one PR (or one PR per bank profile if large).
