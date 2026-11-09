---
plan_id: import-preview-final-description
title: mBank rows carry their final description from parse time
area: import
effort: small
status: archived
archived_at: 2026-11-09
roadmap_ref: ../../roadmap.md
---

# mBank rows carry their final description from parse time

## Intent

The preview step of `/import` shows, for an mBank file, the raw `Opis operacji`
column: every card purchase reads `ZAKUP PRZY UŻYCIU KARTY`, every transfer
`PRZELEW ZEWNĘTRZNY WYCHODZĄCY`. The stored rows get a different description,
built at commit time by `_build_mbank_description`
(`src/kaleta/services/import_service.py:1195`): `Nadawca/Odbiorca — Tytuł`, or
`Tytuł` for card purchases (`LIDL KASPROWICZA 01/INOWROCLAW`).

On 2026-11-09 this made a correct file look broken — as if every merchant name
would be lost — and the import was paused to read the code.

The Wise path already solves this the right way: `_apply_wise_descriptions`
(`import_service.py:~1553`) writes the final text into `ParsedRow.description`
during `parse_queued_file`, so the preview, the duplicate check and the commit
all read one field.

## Scope

In scope:

- In `parse_queued_file`, for `profile == "mbank"`, set each
  `row.description = _build_mbank_description(row.raw)` (mirroring the Wise branch).
- `to_transaction_creates_with_payees` uses `row.description` instead of calling
  `_build_mbank_description` again.
- No signature change to `build_preview_table_rows` or `PreviewSection.render`.
- Test `test_mbank_preview_shows_final_description`: an mBank card row with
  `Opis operacji = ZAKUP PRZY UŻYCIU KARTY`, empty `Nadawca/Odbiorca`, and
  `Tytuł = "LIDL KASPROWICZA 01/INOWROCLAW  DATA TRANSAKCJI: 2026-10-10"` → the
  parsed row and the preview row both read `LIDL KASPROWICZA 01/INOWROCLAW`.
- Test `test_mbank_commit_description_unchanged`: the stored description for a
  transfer row is still `Nadawca/Odbiorca — Tytuł` (regression guard for the
  duplicate check, which compares descriptions exactly).

Out of scope:

- Payee or category columns in the preview.
- The type column (see `import-mbank-transfer-account-suffix`).
- The preview's 70-character truncation (`import_service.py:158`).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_import_service.py -q -k "mbank_preview_shows_final_description or mbank_commit_description_unchanged"`
- `uv run pytest tests/unit/services/test_mbank_real_exports.py -q`
- `grep -c "KAL-CSV-040" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- `[manual]` Upload an mBank statement: the preview's DESCRIPTION column shows
  merchant / counterparty names; the stored row's description starts with the
  same text (the preview cuts at 70 characters).

## Touchpoints

- `src/kaleta/services/import_service.py` — `parse_queued_file`,
  `to_transaction_creates_with_payees`, `_build_mbank_description`
- `tests/unit/services/test_import_service.py`
- `docs/bdd.md` — `KAL-CSV-040`

## Open questions

None. (`build_preview_table_rows` has no API caller — only
`preview_section.py` and tests.)

## Implementation notes

- **Parse time.** The mBank branch of `parse_queued_file` returns
  `_apply_mbank_descriptions(result.rows)`. That module-level helper sits next
  to `_build_mbank_description` and mirrors `_apply_wise_descriptions`; it uses
  `dataclasses.replace`, so `raw` and `notes` are carried over untouched. The
  generic profile that auto-detects mBank takes the same branch (unit test
  `test_mbank_auto_detected_file_gets_final_description`).
- **Commit.** `to_transaction_creates_with_payees` reads `row.description`.
  Its only production caller (`views/import_view/page.py`, mBank branch)
  passes `queued_file.parsed_rows`, which come from `parse_queued_file`, so the
  stored text is unchanged. The existing `TestToTransactionCreatesWithPayees`
  tests build `ParsedRow`s by hand and assert types and payees only, never the
  description, so they are unaffected. `build_preview_table_rows` and
  `PreviewSection.render` are unchanged, as scoped.
- **Coverage lives in `tests/integration`.** `scripts/spec_coverage.py` counts
  `Covers:` only in `tests/integration` and `tests/e2e`. The two unit tests
  the plan names (and its acceptance criterion selects) stay in
  `tests/unit/services/test_import_service.py`. KAL-CSV-040 is covered by
  `tests/integration/test_mbank_final_description.py`, which drives the import
  page's commit path through the services: parse → preview → creates →
  `filter_duplicates` → `create_bulk`. It checks the preview text, the stored
  descriptions, and that a second import of the same file writes 0 rows (the
  duplicate check reads the same text).
- With the service change reverted, all three new unit tests fail.
- `KAL-CSV-039` is left free: the sibling plan
  `import-mbank-transfer-account-suffix` reserves it.

## Implementation (filled by plan-archiver)

## Implementation

Landed on 2026-11-09 (PR #404).

| SHA | Author | Date | Message |
|---|---|---|---|
| `e0aaa990` | Dawid Adamski | 2026-11-09 | Merge pull request #404 from DawidAdamski/plan/import-preview-final-description |

**Files changed:**
- docs/bdd.md
- docs/plans/import-preview-final-description.md
- src/kaleta/services/import_service.py
- tests/integration/test_mbank_final_description.py
- tests/unit/services/test_import_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
