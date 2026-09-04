# Wise (TransferWise) export fixtures

Anonymized from maintainer dogfood — Japan trip JPY wallet, Q2 2026.

## Supported formats

| Format | Import support |
|--------|----------------|
| **CSV** | Yes — select **Wise** profile (auto-detected from `TransferWise ID` header) |
| **QIF** | Yes — same **Wise** profile (auto-detected from `!Type:Bank` + `NCARD-*` / `NTRANSFER-*` ids) |
| MT940 | Planned — [`import-wise-mt940`](../../../../../docs/plans/import-wise-mt940.md) |
| XLSX | Planned — [`import-wise-xlsx`](../../../../../docs/plans/import-wise-xlsx.md) |

Wise UI offers all four for the same statement; Kaleta's upload widget accepts
`.csv` and `.qif`. CSV has the richest columns (merchant, exchange metadata).
QIF carries date, amount, payee, transaction id and memo only:

- **No currency anywhere in the file.** Wise puts it in the download name
  (`statement_<id>_JPY_<from>_<to>.qif`), so the metadata banner shows the
  period and leaves currency blank. The currency-mismatch guard in
  `validate_import_readiness` therefore cannot fire on a QIF import.
- **`M` is not a transaction memo.** It holds the card holder and last four
  (`Jan Kowalski 1234`), byte-identical on every card row, or a copy of the
  payee on top-ups. It is parsed but never persisted.

## Export path in Wise

Statements → choose period → **CSV** or **QIF** → Generate.

Both sample files hold the same 9 transactions. The QIF export is
**English-only** where the CSV is Polish (`Topped up account` vs
`Doładowanie konta`), dates are US `MM/DD/YYYY` against the CSV's
`DD-MM-YYYY`, amounts have no decimal part (`T-51571`), and the fields
come in `D N T P M` order. Take expected values from the matching
fixture, never across the two.

Optional: enable “Display transactions with fees shown separately” if you need
fee rows as separate lines (not covered by the current sample).

## Anonymization applied

- Card holder → `Jan Kowalski` (CSV `Card Holder Full Name`, QIF `M`)
- Card last four → `1234`
- Nothing else altered: the QIF fixture is byte-identical to the real
  export on every `D` / `N` / `T` / `P` line
- TransferWise transaction IDs kept as opaque tokens (no PII)
