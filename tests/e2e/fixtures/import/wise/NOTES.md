# Wise (TransferWise) export fixtures

Anonymized from maintainer dogfood — Japan trip JPY wallet, Q2 2026.

## Supported format

| Format | Import support |
|--------|----------------|
| **CSV** | Yes — select **Wise** profile (auto-detected from `TransferWise ID` header) |
| QIF | Not yet — export CSV from Wise instead |
| MT940 | Not yet — export CSV from Wise instead |
| XLSX | Not yet — export CSV from Wise instead |

Wise UI offers all four for the same statement; Kaleta's upload widget accepts
`.csv` only. CSV has the richest columns (merchant, exchange metadata).

## Export path in Wise

Statements → choose period → **CSV** → Generate.

Optional: enable “Display transactions with fees shown separately” if you need
fee rows as separate lines (not covered by the current sample).

## Anonymization applied

- Card holder → `Jan Kowalski`
- Card last four → `1234`
- TransferWise transaction IDs kept as opaque tokens (no PII)
