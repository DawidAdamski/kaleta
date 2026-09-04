---
plan_id: import-wise-qif
title: Import — Wise QIF statement format
area: import
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#import
---

# Import — Wise QIF statement format

## Intent

Wise lets users export the same statement as **QIF** (personal finance
tools). Some users may prefer QIF over CSV. Kaleta already ships the
**Wise CSV** profile ([`import-bank-profiles`](archive/import-bank-profiles.md),
PR #64); this plan adds QIF as an alternate entry path for the same
wallet transactions.

## Scope

- Anonymized dogfood fixture:
  `tests/e2e/fixtures/import/wise/jpy-travel-sample.qif` (same 9 rows
  as `jpy-travel-sample.csv`).
- QIF parser branch (or shared helper) under `ImportService` — fields:
  `D` date (US `MM/DD/YYYY`), `T` amount, `P` payee, `N` reference id,
  `M` memo, record separator `^`.
- Extend upload `accept` to include `.qif` when Wise profile selected
  (or auto-detect `!Type:Bank` + Wise transaction id pattern).
- Reuse Wise metadata banner (currency JPY, period from min/max dates).
- Unit tests against fixture; optional e2n only if upload UX changes
  materially.

Out of scope:

- Generic QIF from Quicken/other banks (Wise-shaped QIF only until another
  fixture exists).
- QIF export from Kaleta.
- Fee-split rows (Wise option “Display transactions with fees shown
  separately”) — follow-up if a fixture lands.

## Acceptance criteria

- `test -f tests/e2e/fixtures/import/wise/jpy-travel-sample.qif`
- `uv run pytest tests/unit/services/test_wise_qif_import.py -q`
- `grep -q "is_wise_qif" src/kaleta/services/import_service.py`
- `uv run pytest tests/unit/services/test_import_profiles.py -q`
- `uv run python scripts/spec_coverage.py`

## Touchpoints

- `src/kaleta/services/import_service.py` — QIF parse path
- `src/kaleta/views/import_view/upload_section.py` — `accept=.csv,.qif`
- `tests/e2e/fixtures/import/wise/NOTES.md` — mark QIF supported
- `src/kaleta/i18n/locales/en.json` / `pl.json` — upload hint tweak
- BDD: extend or add `KAL-CSV-*` when e2e covers QIF upload

## Open questions

- Auto-detect QIF as Wise vs require profile picker? **Prefer detect**
  when content starts with `!Type:Bank` and `N` lines match
  `CARD-*` / `TRANSFER-*` (same ids as CSV fixture).
- English-only QIF from Wise (per Wise UI) — descriptions may differ
  from Polish CSV (`Topped up account` vs `Doładowanie konta`); tests
  must use BDD literals from the QIF fixture, not CSV.

## Depends on

- Wise CSV profile merged (`import-wise-fixtures` / PR #64).

## Implementation notes

Dogfood sample available (maintainer Japan trip JPY wallet, 2026-04-01 —
2026-06-30). Anonymize holder name and card digits before committing
fixture (see `tests/e2e/fixtures/import/README.md`).

### Resolved open questions

- **Auto-detect vs profile picker** — took the plan default (*prefer
  detect*). `is_wise_qif_content()` requires **both** `!Type:Bank` in the
  first 64 bytes **and** an `N` line matching `CARD-` / `TRANSFER-` /
  `BALANCE-`. `!Type:Bank` alone is generic QIF, so it cannot identify a
  dialect on its own; the Wise transaction id in `N` is the same token as
  the CSV export's `TransferWise ID` column, and that pairing is what
  claims the file. A Quicken-style QIF is deliberately left unclaimed
  (out of scope) and falls through to the generic path.
  `is_wise_content()` now answers for CSV **or** QIF so the registry entry
  keeps its single `detect` callable — `test_import_profiles` still
  asserts `BANK_PROFILES[wise].detect is is_wise_content`.
- **English QIF vs Polish CSV** — confirmed and enforced. The QIF fixture
  reads `Topped up account` where the CSV reads `Doładowanie konta`, and
  its dates are US `MM/DD/YYYY` against the CSV's `DD-MM-YYYY`. Every
  expected value in `test_wise_qif_import.py` is a literal from the QIF
  fixture; `test_qif_descriptions_are_english_not_the_csv_polish` guards
  against a future cross-fixture copy-paste.

### Decisions a reviewer should know

- **QIF does not route through `parse_csv`.** It is not a CSV, so
  `_parse_wise_qif` parses records directly and, unlike the mBank and Wise
  CSV branches, has **no generic-mapping fallback** — handing a QIF to the
  column-mapping step would only render a garbled table. A QIF that yields
  no rows fails with the new `import.qif_no_rows` key instead.
- **Currency is derived from the memos.** QIF has no currency field at
  all, yet the plan asks the Wise metadata banner to show `JPY`. Wise's
  English card memos embed it after the amount (`Card transaction of
  50220 JPY issued by …`), which is the only in-file source, so
  `_QIF_MEMO_CURRENCY` takes the most common trailing 3-letter code.
  When no memo names one the currency stays **empty**, which is the safe
  default: `validate_import_readiness` skips the currency-mismatch block
  on a falsy currency, so an unknown currency never wrongly blocks an
  import.
- **Amounts are parsed with explicit separators** (`decimal="."`,
  `thousands=","`). `_parse_amount`'s auto mode reads `-1,811.00` as
  `-1.811` (EU convention); QIF is US-shaped, so the separators must be
  pinned. `test_amount_with_thousands_separator_is_not_mangled` covers it.
- **Memo is kept as notes only when it adds information** — description is
  `P` (payee) falling back to `M`; `notes` holds `M` only when it differs
  from the description, so top-up rows do not store the same string twice.
- **`accept` widened to `.csv,.qif` for every profile**, not just Wise.
  The widget is built once, before a profile is known, and a QIF dropped
  under *Generic CSV* is promoted to Wise by detection anyway — a
  profile-conditional `accept` would only reject files the parser handles.

### Fixture provenance — needs a maintainer diff

`jpy-travel-sample.qif` was authored to the **field spec written in this
plan** (`D` US `MM/DD/YYYY`, `T`, `P`, `N`, `M`, `^`), mirroring the nine
rows of `jpy-travel-sample.csv` — it is *not* a dump of a real Wise QIF
export, which was not available in this session.
`tests/e2e/fixtures/import/README.md` asks for a real collected file
before shipping a parser, so before relying on this path the maintainer
should export one real Wise QIF and diff it against the fixture,
particularly the `D` date format and the English memo wording the
currency derivation depends on. Both are single-constant changes
(`WiseQifPreprocessor._DATE_FORMAT`, `_QIF_MEMO_CURRENCY`) if the real
export differs.

### Out of scope, left alone

- `import.drop_hint_mbank` / `import.drop_hint_wise` are dead i18n keys —
  `upload_section.py` only ever renders `drop_hint_generic`. Both were
  updated for consistency but wiring them up is a separate chore.
- The BDD feature block is still titled *mBank CSV Import* while already
  holding the Wise CSV scenario (KAL-CSV-019) and now the QIF one
  (KAL-CSV-022). Renaming it is a docs change outside this plan's scope
  (Working Agreement §9).
