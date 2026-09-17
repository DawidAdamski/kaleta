# Wise (TransferWise) export fixtures

Anonymized from maintainer dogfood — Japan trip JPY wallet, Q2 2026.

## Supported formats

| Format | Import support |
|--------|----------------|
| **CSV** | Yes — select **Wise** profile (auto-detected from `TransferWise ID` header) |
| **QIF** | Yes — same **Wise** profile (auto-detected from `!Type:Bank` + `NCARD-*` / `NTRANSFER-*` ids) |
| **MT940** | Yes — same **Wise** profile (auto-detected from `:61:` statement lines + Wise's `TRWI` bank code in `:25:`) |
| XLSX | Planned — [`import-wise-xlsx`](../../../../../docs/plans/import-wise-xlsx.md) |

Wise UI offers all four for the same statement; Kaleta's upload widget accepts
`.csv`, `.qif` and `.mt940` (plus `.940` / `.sta`, the other extensions the same
SWIFT statement arrives under). CSV has the richest columns (merchant, exchange
metadata). QIF carries date, amount, payee, transaction id and memo only:

- **No currency anywhere in the file.** Wise puts it in the download name
  (`statement_<id>_JPY_<from>_<to>.qif`), which `parse_wise_filename` reads —
  that is the only currency a QIF import has, and what lets the
  currency-mismatch guard in `validate_import_readiness` fire on this path.
  This fixture is stored under a descriptive name, not a Wise one, so tests
  that need the currency upload its bytes under the Wise shape (see
  `WISE_QIF_DOWNLOAD_NAME` in `tests/e2e/test_csv_import.py`). Uploaded under
  any other name the currency is blank, as it was before the name was read —
  unknown, which must never block.
- **`M` is not a transaction memo.** It holds the card holder and last four
  (`Jan Kowalski 1234`), byte-identical on every card row, or a copy of the
  payee on top-ups. It is parsed but never persisted.

## MT940 (`jpy-travel-sample.mt940`)

Accounting-minimal. What it has that the QIF does not, and what it lacks:

- **It states its own currency**, in the `:60F:` / `:62F:` balance fields
  (`C260331JPY0,`). No download name has to be read for the currency-mismatch
  guard to fire, so a renamed MT940 is guarded exactly as the original is —
  the one thing the QIF path cannot do.
- **It names no merchant at all.** Where the CSV has `Japanpost Bank(245950)
  GIFU`, MT940 offers only the Wise transaction id on the second line of
  `:61:` (`CARD-3802617048`). That id is what the ledger gets; the plan's open
  question settled on accepting it for v1 rather than inventing a lookup.
- **`:86:` appears on top-ups only**, as an exchange-rate hint
  (`/EXCH/43,5034/` — the same 43.50340 the CSV's `Exchange Rate` column
  carries for `TRANSFER-2134191896`). It is kept in the parsed row's `raw`,
  never used as a description: a rate does not say what was bought.
- Amounts use SWIFT's comma decimal separator and JPY has no decimal part, so
  they are written `51571,`.

### Provenance

The real export, with three identifying values replaced and nothing else
touched — CRLF line endings, the `{1:…}{2:…}{4:` envelope, the trailing `-}`
and the entry order are the bank's own bytes:

| Replaced | With |
|---|---|
| Wise wallet id in `:20:` | `12345678/26/1` |
| IBAN in `:25:` | `GB33TRWI23145600000123` |
| SWIFT session id in `{2:` | `I940000012345678N` |

Three things the format does that are easy to guess wrong, all asserted in
`tests/unit/services/test_wise_mt940_import.py`:

- **Entries run newest-first**, against the oldest-first order the opening and
  closing balances imply. The parser dates each entry from its own `:61:` and
  never depends on the order.
- **Every entry is `FMSC`**, top-ups included — the type code does not
  distinguish a card purchase from a transfer, so nothing may be inferred from
  it.
- **The balance dates are the requested period** (`:60F:` 31 Mar, `:62F:`
  30 Jun), not the first and last movement (17 Apr – 17 May). The metadata
  banner takes its period from the entries.

## Export path in Wise

Statements → choose period → **CSV**, **QIF** or **MT940** → Generate.

All three sample files hold the same 9 transactions. The QIF export is
**English-only** where the CSV is Polish (`Topped up account` vs
`Doładowanie konta`), dates are US `MM/DD/YYYY` against the CSV's
`DD-MM-YYYY`, amounts have no decimal part (`T-51571`), and the fields
come in `D N T P M` order, and MT940 says less than either (see above).
Take expected values from the matching fixture, never across them.

Optional: enable “Display transactions with fees shown separately” if you need
fee rows as separate lines (not covered by the current sample).

## Anonymization applied

- Card holder → `Jan Kowalski` (CSV `Card Holder Full Name`, QIF `M`; MT940
  names no holder at all)
- Card last four → `1234`
- Nothing else altered: the QIF fixture is byte-identical to the real
  export on every `D` / `N` / `T` / `P` line
- Wise IBAN → `GB33TRWI23145600000123` (MT940 `:25:`), keeping the country,
  bank-code and length shape of the real one
- TransferWise transaction IDs kept as opaque tokens (no PII)
- The Wise `<account_id>` segment of the download name identifies the real
  wallet, so tests use an anonymized `12345678` rather than the real one
