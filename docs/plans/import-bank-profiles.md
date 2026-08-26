---
plan_id: import-bank-profiles
title: Import — bank profiles from real export fixtures
area: import
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#import
---

# Import — bank profiles from real export fixtures

## Intent

Daily import currently has two working formats: **generic CSV** (header
alias parser) and **mBank** (metadata preprocessor + auto-detect). Other
banks the user actually uses (seed data mentions PKO, Revolut, etc.) fall
through to the generic parser, which may mishandle encoding, delimiters,
or column shapes.

Add bank-specific profiles **only when driven by real, anonymized export
fixtures** collected during dogfooding — never by inventing parsers from
docs or memory. Distinct from
[`import-per-file-mapping-memory`](archive/import-per-file-mapping-memory.md)
(filename → account/column memory); this plan is about format detection
and parsing.

## Scope

- Document the fixture contribution process for new bank samples.
- Make extension points in the import profile registry / `import_service`
  / view constants obvious so a later PR can add one bank at a time.
- For each **existing** non-mBank anonymized fixture in the repo: add a
  profile, unit test, and (when UI-visible) i18n keys.
- Retag / add `KAL-CSV-*` scenarios only when a profile lands with tests.

Out of scope:

- Speculative PKO / Revolut / other profiles without real fixtures.
- Per-file mapping memory (`import-per-file-mapping-memory`).
- Open banking / PSD2 connectivity.
- Changing mBank behaviour beyond shared registry wiring.

## Acceptance criteria

- `test -f tests/e2e/fixtures/import/README.md`
- `uv run pytest tests/unit/services/test_import_profiles.py -q`
- `grep -q "BankProfileSpec" src/kaleta/services/import_profiles.py`
- `grep -q "detect_bank_profile" src/kaleta/services/import_service.py`
- `[manual]` No enabled UI profile exists for a bank that lacks an
  anonymized fixture under `tests/e2e/fixtures/` (or
  `tests/e2e/fixtures/import/`).
- `[manual]` When a dogfood fixture arrives: follow the README checklist
  in a dedicated follow-up PR (one bank per PR).

Partially unmet until dogfood files exist:

- ~~`[blocked]` At least one non-mBank bank profile with fixture-backed
  unit test~~ — **Wise** landed 2026-08-26 (see Implementation notes).

## Touchpoints

- `src/kaleta/services/import_profiles.py` — registry + detection
  extension point (new).
- `src/kaleta/services/import_service.py` — wire auto-detect through
  registry; keep mBank preprocessor.
- `src/kaleta/views/import_view/constants.py` — profile list from
  registry.
- `tests/e2e/fixtures/import/README.md` — contribution guide.
- `tests/unit/services/test_import_profiles.py` — registry contracts.
- `docs/plans/README.md` — index entry.
- Per-bank later: i18n keys, preprocessor, BDD `KAL-CSV-*`, e2e fixture.

## Open questions

- Should new bank fixtures live only under `tests/e2e/fixtures/import/`
  while the historical mBank e2e file stays at
  `tests/e2e/fixtures/mbank_transfer.csv`? **Yes** — avoid churn on
  existing e2e paths; new banks use the subdirectory.
- Who supplies dogfood files? Maintainer / early users; strip PII before
  commit (see fixture README).

## Implementation notes

### 2026-07-27 — reset to draft; scaffold complete, waiting on fixtures

Scaffold shipped in `db7d0f3` / PR #29; reset to `draft` until a real non-mBank
anonymized fixture arrives. Not active WIP.

### 2026-07-26 — scaffolding only (profiles blocked on dogfood)

**Fixtures audit:** the only bank export fixture in the repo is
`tests/e2e/fixtures/mbank_transfer.csv`. No anonymized PKO, Revolut, or
other non-mBank samples exist. Per plan constraint, **no speculative
bank profiles** were added.

**Landed:**

- `src/kaleta/services/import_profiles.py` — `BankProfileSpec` registry,
  `detect_bank_profile()`, UI row helper; docstring checklist for the
  next bank.
- `ImportService.parse_queued_file` auto-detect goes through the
  registry; comment marks where the next parse branch belongs.
- View `_PROFILES` reads from the registry (single source of truth).
- `tests/e2e/fixtures/import/README.md` — layout + anonymization +
  contribution checklist.
- Unit tests lock enabled keys to `{generic, mbank}` only.

**Blocked / acceptance partially unmet:**

- First non-mBank profile + fixture-backed test — waiting on dogfood
  files. Follow-up: one PR per bank after a sample lands under
  `tests/e2e/fixtures/import/<profile_id>/`.

**Not in this branch:** `import-per-file-mapping-memory` (distinct plan).

### 2026-08-26 — Wise profile (first non-mBank bank)

**Fixtures:** Anonymized JPY travel wallet CSV under
`tests/e2e/fixtures/import/wise/jpy-travel-sample.csv`. Maintainer also
supplied QIF, MT940, and XLSX for the same statement — documented in
`NOTES.md` as unsupported (upload accepts `.csv` only; use CSV export).

**Landed:**

- `WISE_PROFILE` + auto-detect (`TransferWise ID` header)
- `WisePreprocessor` — currency/period metadata from rows
- Merchant-first descriptions (cleaner than verbose PL card text)
- Currency mismatch guard (same as mBank)
- Unit tests: `test_wise_real_exports.py`
- BDD: `KAL-CSV-019 @automated`

**Still open:** PKO / Revolut profiles when exports arrive.
