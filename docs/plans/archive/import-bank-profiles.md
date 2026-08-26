---
plan_id: import-bank-profiles
title: Import — bank profiles from real export fixtures
area: import
effort: medium
status: archived
archived_at: 2026-08-26
roadmap_ref: ../../roadmap.md#import
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
[`import-per-file-mapping-memory`](import-per-file-mapping-memory.md)
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

### 2026-08-26 — real mBank dogfood fixtures (credit + ROR)

**Fixtures:** `tests/e2e/fixtures/import/mbank/` — credit card + ROR samples.
Transfer detection via `Numer konta`; date alias `Data księgowania`.
**Tests:** `test_mbank_real_exports.py`. **PR #63.**

### 2026-08-26 — Wise profile (first non-mBank bank)

**Fixtures:** `tests/e2e/fixtures/import/wise/jpy-travel-sample.csv`.
**PR #64.** BDD `KAL-CSV-019 @automated`.

**Follow-up (separate draft plans, not this plan):**

- [`import-wise-qif.md`](../import-wise-qif.md)
- [`import-wise-mt940.md`](../import-wise-mt940.md)
- [`import-wise-xlsx.md`](../import-wise-xlsx.md)

**Future banks (PKO / Revolut):** use the fixture README checklist — one
bank per PR; no standing plan required.

## Implementation

Landed across PR #29 (scaffold), #63 (mBank fixtures), #64 (Wise); archived
2026-08-26.

| SHA | Author | Date | Message |
|---|---|---|---|
| `db7d0f3` | — | 2026-07 | Import profile registry scaffold (PR #29) |
| `858007c` | Dawid Adamski | 2026-08-26 | Merge PR #63 — mBank real export fixtures |
| `d69511f` | Dawid Adamski | 2026-08-26 | Merge PR #64 — Wise CSV profile |

**Profiles enabled:** `generic`, `mbank`, `wise` — each fixture-backed.

**Acceptance criteria run** (archiver, 2026-08-26):

| Command | Exit |
|---|---|
| `` `test -f tests/e2e/fixtures/import/README.md` `` | 0 |
| `` `uv run pytest tests/unit/services/test_import_profiles.py -q` `` | 0 (7 passed) |
| `` `grep -q "BankProfileSpec" src/kaleta/services/import_profiles.py` `` | 0 |
| `` `grep -q "detect_bank_profile" src/kaleta/services/import_service.py` `` | 0 |

**Notes:** PKO/Revolut remain out of scope until dogfood exports arrive.
Extension process lives in `tests/e2e/fixtures/import/README.md`.
