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
`.csv` and `.qif`. CSV has the richest columns (merchant, exchange metadata);
QIF carries date, amount, payee, transaction id and memo only, and names no
currency — the metadata banner derives it from the English card memos
(`Card transaction of 50220 JPY issued by …`) and stays blank when absent.

## Export path in Wise

Statements → choose period → **CSV** or **QIF** → Generate.

Both sample files hold the same 9 transactions. The QIF export is
**English-only** where the CSV is Polish (`Topped up account` vs
`Doładowanie konta`) and dates are US `MM/DD/YYYY`, so tests must take
expected values from the matching fixture, never across the two.

Optional: enable “Display transactions with fees shown separately” if you need
fee rows as separate lines (not covered by the current sample).

## Anonymization applied

- Card holder → `Jan Kowalski`
- Card last four → `1234`
- TransferWise transaction IDs kept as opaque tokens (no PII)
