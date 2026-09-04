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
- **English QIF vs Polish CSV** — confirmed against the real export. It
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
- **Currency is empty — the plan's "banner shows JPY" is not
  achievable.** See *Fixture provenance* below: the real export names no
  currency anywhere. Wise puts it in the download filename
  (`statement_<id>_JPY_<from>_<to>.qif`), which `parse_queued_file` never
  receives. Empty is the correct value rather than a guess, and it is
  inert for readiness (`validate_import_readiness` skips the
  currency-mismatch block on a falsy currency), **but that is precisely
  the gap**: a JPY QIF imported into a PLN account is not stopped, where
  the CSV path would stop it. Closing it means threading the upload
  filename into parsing — a signature change across the view, deliberately
  left out of this plan. **Owner decision, see the follow-up below.**
- **Amounts are parsed with explicit separators** (`decimal="."`,
  `thousands=","`). `_parse_amount`'s auto mode reads `-1,811.00` as
  `-1.811` (EU convention); QIF is US-shaped, so the separators must be
  pinned. `test_amount_with_thousands_separator_is_not_mangled` covers it.
- **The memo is never persisted.** `M` is not a transaction memo: the real
  export puts the card holder and last four there (`Jan Kowalski 1234`),
  byte-identical on all seven card rows, and a copy of the payee on the
  two top-ups. Description is `P` alone — falling back to `M` would write
  the holder's name into the ledger — and `notes` stays empty.
  `test_card_holder_memo_never_reaches_the_ledger` and an e2e absence
  assertion pin this.
- **`accept` widened to `.csv,.qif` for every profile**, not just Wise.
  The widget is built once, before a profile is known, and a QIF dropped
  under *Generic CSV* is promoted to Wise by detection anyway — a
  profile-conditional `accept` would only reject files the parser handles.

### Fixture provenance — resolved against the real export

The fixture was first authored to the field spec written in this plan,
then **replaced with the maintainer's real Wise export** (`test_data/
statement_136577258_JPY_2026-04-01_2026-06-30.qif`, supplied mid-task and
deliberately not committed — it holds live PII). Only the card-holder
memos were anonymized; every `D` / `N` / `T` / `P` line is byte-identical
to the real file.

The real export confirmed one assumption and broke two:

| Plan assumption | Real export | Effect |
|---|---|---|
| `D` is US `MM/DD/YYYY` | ✅ `D05/17/2026` | none |
| field order `D T P N M` | `D N T P M` | none — the parser keys off the letter, not position (`test_field_order_in_the_real_export_is_not_assumed`) |
| decimal amounts | `T-51571`, no decimal part | none — pinned separators handle both |
| banner shows currency `JPY` | **no currency anywhere in the file** | dropped the memo-sniffing regex; currency is empty, and the mismatch guard cannot fire (see above) |
| `M` is a transaction memo | **card holder + last four**, same on every card row | `M` is no longer persisted; it would have written the holder's name into every imported transaction |

The second and third rows are the reason to insist on a real fixture: a
hand-authored one had passed 23 green tests while encoding a memo format
Wise does not emit.

### Follow-up for the owner (not done here)

Derive the wallet currency from the Wise download filename
(`statement_<id>_<CCY>_<from>_<to>`) so the currency-mismatch guard
covers QIF as it does CSV. It needs `parse_queued_file` to take the
filename, so it is a scope change, not a fix — raise it as an issue
rather than folding it into this PR. `test_data/` also holds real
`.mt940` and `.xlsx` exports for the two sibling plans.

### Out of scope, left alone

- `import.drop_hint_mbank` / `import.drop_hint_wise` are dead i18n keys —
  `upload_section.py` only ever renders `drop_hint_generic`, so the
  reworded `drop_hint_wise` will not actually be seen. `drop_hint_mbank`
  was left untouched; wiring either up is a separate chore.
- **`inherit_queue_settings` cannot copy the account between QIF files.**
  Its Wise arm keys off `metadata.currency`, which QIF leaves empty, so
  two queued QIFs fall through to the generic same-profile branch: the
  categories and skip-duplicates flag still propagate, the target account
  does not. Correct behaviour (the account is a real choice, and there is
  no currency to confirm the files match), just less convenient than the
  CSV path. Fixed for free by the filename follow-up above.
- **The active profile button is only tinted, not filled.**
  `set_active_profile` sets `color=primary unelevated`, but the build-time
  `flat` prop is never removed, so Quasar renders `q-btn--flat
  text-primary` and the `unelevated` never applies. Cosmetic, pre-existing,
  and shared by all three profiles — the e2e asserts what actually renders
  (`text-primary` vs `text-grey-4`) rather than papering over it. Chore
  inbox, not this PR.
- **Per-record QIF parse errors have no render path.** `_parse_wise_qif`
  puts them in `errors`, but the failed-status branch in `page.py` shows
  `error_key` only, and `mapping_section` (the sole renderer of
  `parse_errors`) is generic-profile-only. A QIF whose records all fail
  for a concrete reason shows just the generic `import.qif_no_rows`. This
  follows from the deliberate no-mapping-fallback design; surfacing the
  detail is a follow-up, not a change to make here.
- The BDD feature block is still titled *mBank CSV Import* while already
  holding the Wise CSV scenario (KAL-CSV-019) and now the QIF one
  (KAL-CSV-022). Renaming it is a docs change outside this plan's scope
  (Working Agreement §9).
