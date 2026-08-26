# Import bank-export fixtures

Anonymized CSV samples that drive **bank import profiles**. Kaleta only
ships a profile when a real export format is proven by a fixture here
(or, for historical mBank e2e coverage, `../mbank_transfer.csv`).

Do **not** invent PKO / Revolut / other parsers from documentation or
memory. Collect a real file during dogfooding first.

## Layout

```
tests/e2e/fixtures/import/
  README.md                 ← this file
  <profile_id>/
    sample.csv              ← minimal anonymized export (required)
    NOTES.md                ← optional: export path in the bank UI, quirks
```

Example: `wise/jpy-travel-sample.csv` (JPY travel wallet, CSV export).

`profile_id` must match the registry key in
`src/kaleta/services/import_profiles.py` (e.g. `mbank`, later `pko` only
after a real file arrives).

Existing mBank Playwright fixture (do not relocate without updating
e2e paths):

- `tests/e2e/fixtures/mbank_transfer.csv`

## Anonymization checklist

Before committing a sample:

1. Replace account holder name with a fake (e.g. `Jan Kowalski`).
2. Replace IBAN / account numbers with clearly fake digits that keep
   the same length and spacing style as the real export.
3. Replace card numbers, phone numbers, and street addresses.
4. Keep **structure** intact: metadata headers, delimiters, encodings,
   column names, date/amount formats, footer lines.
5. Prefer 3–10 representative rows (card purchase, transfer, income)
   over a full month dump.
6. Confirm the file opens as the bank intended (encoding: try
   UTF-8 / Windows-1250 if Polish diacritics matter).

Never commit live production exports with real PII.

## Adding a profile (after the fixture exists)

Follow the module docstring checklist in
`src/kaleta/services/import_profiles.py`:

1. Place `sample.csv` under `import/<profile_id>/`.
2. Implement preprocessor + `BankProfileSpec` + `parse_queued_file` branch.
3. Add `import.profile_<profile_id>` to `en.json` / `pl.json`.
4. Unit-test against the fixture; one bank per PR.
5. Add or retag BDD `KAL-CSV-*` when behaviour is covered.

Related but separate: filename → mapping memory is
`docs/plans/import-per-file-mapping-memory.md` — do not mix that work
into a bank-profile PR.
