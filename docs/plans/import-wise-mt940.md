---
plan_id: import-wise-mt940
title: Import — Wise MT940 statement format
area: import
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#import
---

# Import — Wise MT940 statement format

## Intent

Wise exports **MT940** (standard banking import). MT940 is common in
accounting tools and may be the format users already batch-import
elsewhere. Add Wise-flavoured MT940 parsing so the same JPY wallet
statement can be imported without converting to CSV.

## Scope

- Anonymized fixture:
  `tests/e2e/fixtures/import/wise/jpy-travel-sample.mt940` (same period
  and 9 movements as CSV fixture).
- MT940 parser for Wise's SWIFT layout:
  - Header `:25:` → account IBAN (metadata)
  - `:60F:` / `:62F:` → opening/closing balance + implicit currency
  - `:61:` → date (YYMMDD), D/C, amount, reference line
  - `:86:` → optional exchange rate hint (`/EXCH/…`) on top-ups
- Map `:61:` continuation lines (`CARD-*`, `TRANSFER-*`) to
  descriptions (reference id + lookup or embedded merchant if absent).
- Upload accepts `.mt940` / `.940` / `.sta` (confirm Wise download
  extension — dogfood file uses `.mt940`).
- Currency mismatch guard like Wise CSV.

Out of scope:

- Full generic MT940 for all banks (PKO, etc.) without fixtures.
- CAMT.053 XML (Wise offers separately).
- Multi-statement files / `:28C:` pagination edge cases until a fixture
  proves them.

## Acceptance criteria

- `test -f tests/e2e/fixtures/import/wise/jpy-travel-sample.mt940`
- `uv run pytest tests/unit/services/test_wise_mt940_import.py -q`
- `grep -q "WiseMt940" src/kaleta/services/import_service.py`
- `uv run pytest tests/unit/services/test_import_profiles.py -q`

## Touchpoints

- `src/kaleta/services/import_service.py` — MT940 tokenizer + Wise mapper
- `src/kaleta/services/import_profiles.py` — detect heuristic (BIC
  `TRWIGB2L` or `:25:GB…TRWI…` in sample)
- `src/kaleta/views/import_view/upload_section.py`
- `tests/e2e/fixtures/import/wise/NOTES.md`
- Optional: store `:25:` digits in metadata `account_number_digits` for
  queue inheritance (like mBank IBAN)

## Open questions

- Wise MT940 lacks merchant names — descriptions will be reference ids
  unless we join with a sidecar or keep MT940 as “accounting minimal”.
  **Accept reference id as description for v1**; document in NOTES.
- Should MT940 reuse `WISE_PROFILE` or sub-key `wise-mt940`? **Same
  profile**, different detect/parse arm (like mBank credit vs ROR variants).

## Depends on

- Wise CSV profile merged (PR #64).

## Implementation notes

Dogfood MT940 structure (maintainer sample):

```
:25:GB65TRWI60846467455991
:61:260517D51571,FMSCNONREF
CARD-3802617048
:86:/EXCH/43,5034/   ← on PLN→JPY top-ups only
```

Anonymize IBAN in fixture; keep length/checksum pattern plausible.

### Decisions taken (2026-09-17)

Both open questions were settled with the plan's own defaults:

- **Descriptions are the Wise transaction id.** MT940 names no merchant
  anywhere — `CARD-3802617048` on `:61:`'s second line is all the format
  offers, so that is what the ledger gets. `:86:` holds only the
  `/EXCH/…/` rate on top-ups; it is kept in the parsed row's `raw` and
  never used as a description, because a rate does not say what was
  bought. The customer reference is the documented fallback for an entry
  with no detail line, except `NONREF` — SWIFT for "none given", which
  names nothing.
- **Same `WISE_PROFILE`, a third detect/parse arm.** `is_wise_content`
  now covers CSV, QIF and MT940; `parse_queued_file` tries MT940 first
  (most specific), then QIF, then CSV. No new profile key, no new i18n
  profile label.

Two things MT940 does better than the QIF path, both now covered:

- **It states its own currency** in `:60F:` / `:62F:`, so `_parse_wise_mt940`
  reads no filename at all. A renamed MT940 is guarded by
  `validate_import_readiness` exactly as the original is — the gap the QIF
  path closes with `parse_wise_filename` does not exist here.
- **`:25:` gives the account**, so `MBankFileMetadata.account_number` and
  `account_number_digits` are populated (the optional touchpoint). Queue
  inheritance still keys Wise files on currency, as it did before; the
  digits only feed the metadata banner today.

### Fixture provenance — needs the maintainer's eye

`jpy-travel-sample.mt940` is **not** a byte-level anonymization of a full
export, unlike the CSV and QIF fixtures beside it. It reproduces the
per-tag lines quoted above verbatim and reconstructs the rest around the
CSV fixture's nine movements. `tests/e2e/fixtures/import/wise/NOTES.md`
lists field by field what is authentic (`:61:` layout, `FMSC`, `NONREF`,
the detail line, `:86:/EXCH/…/`, dates, amounts) and what is not (`:20:`
and `:28C:` values, `FTRF` on top-ups, the `:60F:`/`:62F:` balances,
oldest-first order). The parser depends on none of the reconstructed
parts, and the unit tests assert that — entry order, type codes and
balance amounts are all proven irrelevant.

**Open for the maintainer:** confirm against a real download whether Wise
writes entries oldest-first, and which extension it uses (`.mt940`,
`.940` or `.sta` — the upload widget accepts all three). Neither changes
behaviour; both would let the "reconstructed" list shrink.

### Privacy flag (pre-existing, not introduced here)

The IBAN quoted in the dogfood sample above (`GB65TRWI…`) looks like the
maintainer's real Wise account number, and it is already committed to
this repo. The fixture uses an anonymized `GB33TRWI23145600000123`
instead, keeping the country, `TRWI` bank code and 22-character shape.
Scrubbing the plan's own copy is left to the maintainer — it is their
record, and it is in git history either way.
