---
plan_id: import-wise-mt940
title: Import — Wise MT940 statement format
area: import
effort: medium
status: draft
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
