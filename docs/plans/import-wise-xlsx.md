---
plan_id: import-wise-xlsx
title: Import — Wise XLSX statement format
area: import
effort: medium
status: draft
roadmap_ref: ../roadmap.md#import
---

# Import — Wise XLSX statement format

## Intent

Wise offers **XLSX (Excel)** for the same statement. Users who open
exports in Excel may upload XLSX directly instead of saving as CSV.
Parse the Wise Excel layout and feed the same import pipeline as CSV.

## Scope

- Anonymized fixture:
  `tests/e2e/fixtures/import/wise/jpy-travel-sample.xlsx` (binary;
  same 9 data rows as CSV).
- XLSX reader (likely `openpyxl` — add dependency if not present;
  justify in implementation notes).
- Map columns equivalent to CSV: ID, Date, Amount, Currency,
  Description, Merchant, etc. (English descriptions in XLSX vs Polish
  in CSV — fixture-driven tests).
- Upload `accept` includes `.xlsx` for Wise profile.
- Auto-decode bytes in upload handler before parse (already exists for
  CSV text).

Out of scope:

- Arbitrary Excel bank exports.
- XLS macro-enabled `.xls`.
- Live conversion “open any xlsx as generic CSV” without Wise layout
  detection.

## Acceptance criteria

- `test -f tests/e2e/fixtures/import/wise/jpy-travel-sample.xlsx`
- `uv run pytest tests/unit/services/test_wise_xlsx_import.py -q`
- `grep -q "WiseXlsx" src/kaleta/services/import_service.py`
- `uv run pytest tests/unit/services/test_import_profiles.py -q`
- `grep -q openpyxl pyproject.toml` (or document stdlib-only alternative
  if rejected)

## Touchpoints

- `pyproject.toml` — optional dependency group `import-xlsx`?
- `src/kaleta/services/import_service.py`
- `src/kaleta/views/import_view/upload_section.py`
- `tests/e2e/fixtures/import/wise/NOTES.md`
- CI: ensure new dep synced in verify workflow

## Open questions

- Add `openpyxl` to main deps vs `[project.optional-dependencies]`?
  **Prefer optional extra** until a second XLSX bank exists.
- Wise XLSX uses Excel serial dates — confirm timezone/UTC handling
  matches CSV `Date Time` column for duplicate detection.

## Depends on

- Wise CSV profile merged (PR #64).

## Implementation notes

Dogfood XLSX shared strings include English descriptions (`Card
transaction of …`, `Topped up account`) and same transaction ids as CSV.
Anonymize before commit; keep sheet structure byte-identical aside from
PII cells.
