---
plan_id: import-wise-qif
title: Import — Wise QIF statement format
area: import
effort: small
status: draft
roadmap_ref: ../roadmap.md#import
---

# Import — Wise QIF statement format

## Intent

Wise lets users export the same statement as **QIF** (personal finance
tools). Some users may prefer QIF over CSV. Kaleta already ships the
**Wise CSV** profile ([`import-bank-profiles`](archive/import-bank-profiles.md),
PR #64); this plan adds QIF as an alternate entry path for the same
wallet transactions.

## Scope

- Anonymized dogfood fixture:
  `tests/e2e/fixtures/import/wise/jpy-travel-sample.qif` (same 9 rows
  as `jpy-travel-sample.csv`).
- QIF parser branch (or shared helper) under `ImportService` — fields:
  `D` date (US `MM/DD/YYYY`), `T` amount, `P` payee, `N` reference id,
  `M` memo, record separator `^`.
- Extend upload `accept` to include `.qif` when Wise profile selected
  (or auto-detect `!Type:Bank` + Wise transaction id pattern).
- Reuse Wise metadata banner (currency JPY, period from min/max dates).
- Unit tests against fixture; optional e2n only if upload UX changes
  materially.

Out of scope:

- Generic QIF from Quicken/other banks (Wise-shaped QIF only until another
  fixture exists).
- QIF export from Kaleta.
- Fee-split rows (Wise option “Display transactions with fees shown
  separately”) — follow-up if a fixture lands.

## Acceptance criteria

- `test -f tests/e2e/fixtures/import/wise/jpy-travel-sample.qif`
- `uv run pytest tests/unit/services/test_wise_qif_import.py -q`
- `grep -q "is_wise_qif" src/kaleta/services/import_service.py`
- `uv run pytest tests/unit/services/test_import_profiles.py -q`
- `uv run python scripts/spec_coverage.py`

## Touchpoints

- `src/kaleta/services/import_service.py` — QIF parse path
- `src/kaleta/views/import_view/upload_section.py` — `accept=.csv,.qif`
- `tests/e2e/fixtures/import/wise/NOTES.md` — mark QIF supported
- `src/kaleta/i18n/locales/en.json` / `pl.json` — upload hint tweak
- BDD: extend or add `KAL-CSV-*` when e2e covers QIF upload

## Open questions

- Auto-detect QIF as Wise vs require profile picker? **Prefer detect**
  when content starts with `!Type:Bank` and `N` lines match
  `CARD-*` / `TRANSFER-*` (same ids as CSV fixture).
- English-only QIF from Wise (per Wise UI) — descriptions may differ
  from Polish CSV (`Topped up account` vs `Doładowanie konta`); tests
  must use BDD literals from the QIF fixture, not CSV.

## Depends on

- Wise CSV profile merged (`import-wise-fixtures` / PR #64).

## Implementation notes

Dogfood sample available (maintainer Japan trip JPY wallet, 2026-04-01 —
2026-06-30). Anonymize holder name and card digits before committing
fixture (see `tests/e2e/fixtures/import/README.md`).
