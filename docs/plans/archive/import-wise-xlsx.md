---
plan_id: import-wise-xlsx
title: Import — Wise XLSX statement format
area: import
effort: medium
status: archived
archived_at: 2026-09-18
roadmap_ref: ../../roadmap.md#import
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

### Decisions taken (2026-09-18)

Both open questions settled with the plan's defaults:

- **`openpyxl` in a new `import-xlsx` extra**, not a base dependency —
  one bank offers XLSX and every one of them also offers CSV. It is also
  in the `dev` group, or the acceptance-criteria tests could not run.
  When the extra is absent the upload fails with `import.xlsx_extra_missing`
  naming it, instead of an `ImportError` traceback.
- **Excel serial dates** are resolved by openpyxl against the workbook's
  own epoch — the single job that justifies the dependency. `46159` →
  2026-05-17, matching the CSV row of the same id. No timezone handling is
  needed: the `Date` column is a whole-day serial; `Date Time` carries the
  fractional part and is not read.

### What the real workbook taught us

The fixture is the maintainer's real export (`test_data/`), anonymized in
`xl/sharedStrings.xml` only. Four things the plan could not have known,
each now asserted in `tests/unit/services/test_wise_xlsx_import.py`:

- **The first column is `ID`, not `TransferWise ID`** — the existing CSV
  content heuristic would never have claimed the file.
- **The column order is not the CSV's.** `Total Fees` sits at index 11
  where the CSV has `Payer Name`, so columns are matched by header name.
- **The sheet declares `<dimension ref="A1"/>`**, which is false. A
  `read_only=True` openpyxl load trusts it and yields one cell and zero
  rows; the normal loader is used instead.
- **openpyxl writes no `sharedStrings.xml` for a small workbook**, inlining
  strings in the sheet instead. The detector therefore searches the string
  table *and* the worksheets, or a Wise-shaped book from another writer
  would go unrecognised.

### Binary uploads in a text pipeline

`parse_queued_file` took only decoded text, which a ZIP has none of. It now
also takes `raw: bytes` (default `b""`), and `QueuedFile` carries the
upload's undecoded bytes beside `content`. The XLSX check runs first and on
the bytes alone, before any text heuristic — a workbook decoded as a string
could match nothing anyway. Every text format ignores the new argument.

### Concern for the maintainer

An optional extra means **XLSX import is off in a default install**: the
user uploads `.xlsx`, and is told to install something. For an import
format that is a poor first encounter, and the alternative the acceptance
criteria allowed — a stdlib `zipfile` + XML reader, no dependency at all —
would work for everyone. It was not taken because the plan's stated
preference is the extra. Worth revisiting if XLSX uploads turn out to be
common, or when a second XLSX bank arrives.

## Implementation

Landed on 2026-09-18 (PR #99).

| SHA | Author | Date | Message |
|---|---|---|---|
| `b615134` | Dawid Adamski | 2026-09-18 | Merge pull request #99 from DawidAdamski/plan/import-wise-xlsx |

**Files changed:**
- docs/adr/034-openpyxl-as-an-optional-extra-for-xlsx-import.md
- docs/architecture.md
- docs/bdd.md
- docs/plans/import-wise-xlsx.md
- docs/tech-stack.md
- pyproject.toml
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/services/import_service.py
- src/kaleta/views/import_view/page.py
- src/kaleta/views/import_view/state.py
- src/kaleta/views/import_view/upload_section.py
- tests/e2e/fixtures/import/wise/NOTES.md
- tests/e2e/fixtures/import/wise/jpy-travel-sample.xlsx
- tests/e2e/test_csv_import.py
- tests/unit/services/test_import_profiles.py
- tests/unit/services/test_wise_xlsx_import.py
- uv.lock

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
