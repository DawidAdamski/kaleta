---
adr_id: "034"
title: "openpyxl as an Optional Extra for XLSX Import"
status: accepted
---

# ADR-34: openpyxl as an Optional Extra for XLSX Import

- **Decision**: Read XLSX bank statements with `openpyxl`, shipped in an
  optional `import-xlsx` extra rather than as a base dependency. The text
  statement formats (CSV, QIF, MT940) stay on the standard library.
- **Rationale**: One bank offers XLSX today, and every bank that offers XLSX
  also offers CSV, so a base install should not carry the dependency for it
  (the same reasoning as [ADR-8](008-prophet-for-financial-forecasting.md) for
  Prophet). What earns the dependency at all is Excel serial dates: a workbook
  stores `46159`, not `2026-05-17`, and resolving that against the file's own
  epoch is exactly the job a spreadsheet library exists to do.
- **Rejected alternative**: a dependency-free reader over `zipfile` plus
  `xml.etree`. The Wise sheet is simple enough for it — flat, no formulas, no
  merged cells — and it would make XLSX import work in every install. It was
  not taken because it means owning date-serial and cell-type handling that
  openpyxl already has, for one bank. The trade-off is real and revisitable:
  the cost of the extra is that **XLSX import is off in a default install**,
  and a user who uploads a workbook is told to install something.
- **Consequence**: `WiseXlsxPreprocessor.is_available()` gates the parse path
  and returns `import.xlsx_extra_missing` when the extra is absent, so a base
  install fails with a message instead of an `ImportError`. `openpyxl` and
  `types-openpyxl` are also in the `dev` group so the tests and mypy run.
  Because a workbook is binary, `ImportService.parse_queued_file` takes the
  upload's raw bytes alongside its decoded text.
