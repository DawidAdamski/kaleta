---
plan_id: import-filename-currency-guard
title: Import — currency guard for statements that carry no currency
area: import
effort: medium
status: draft
roadmap_ref: ../roadmap.md#import
---

# Import — currency guard for statements that carry no currency

## Intent

The currency-mismatch guard in `validate_import_readiness` stops a user
importing a JPY statement onto a PLN account. It works by comparing
`metadata.currency` against the target account's currency — and it only
fires when the file names its currency.

**A Wise QIF never does.** Confirmed against a real export
([`import-wise-qif`](archive/import-wise-qif.md), *Fixture provenance*): the body
carries `D` date, `T` amount, `P` payee, `N` id and `M` card holder, and
nothing else. Wise puts the currency in the **download filename**
(`statement_136577258_JPY_2026-04-01_2026-06-30.qif`), which
`parse_queued_file` never receives.

So today a JPY QIF imported onto a PLN account is accepted silently, and
the ledger ends up with 51 571 "PLN" that were really yen. The CSV path
catches exactly this. This plan closes the gap by reading the currency
from the upload filename when — and only when — the content has none.

## Scope

- **Filename metadata parser** in `import_profiles.py`:
  `parse_wise_filename(name)` → currency + period for Wise's
  `statement_<account_id>_<CCY>_<from>_<to>.<ext>` shape, returning
  `None` when the name does not match.
- **Thread the filename into parsing.** `ImportService.parse_queued_file`
  takes a keyword-only `filename: str = ""`. The view already holds it
  (`QueuedFile.filename`) and passes it at both call sites.
- **Content wins; filename fills gaps.** A parsed currency from the
  content (Wise CSV, mBank) is never overridden. The filename only
  supplies what the format cannot.
- **Period stays content-derived.** The QIF body's min/max transaction
  dates are more accurate than the *requested* range in the filename
  (a statement for April–June whose first transaction is 17 April should
  banner 17 April). The filename's dates are parsed but deliberately
  unused for the banner — keep them available for a future
  "file covers a wider period than its rows" hint.
- **Unknown stays unblocked.** A renamed or non-matching file yields no
  currency and the guard stays silent, exactly as today. Failing closed
  would reject legitimate imports of correctly-named files.
- **BDD.** `KAL-CSV-022` currently asserts *"the banner shows no
  currency, because the QIF format carries none"* — that line becomes
  false and must be updated in the same PR. Add a new scenario for the
  block itself.

Out of scope:

- Asking the user to confirm the currency in the UI when it cannot be
  determined (see Open questions — a bigger UX change, and the
  filename covers the normal case).
- Filename parsing for any bank other than Wise. mBank carries its
  currency in the file header already.
- MT940 / XLSX ([`import-wise-mt940`](import-wise-mt940.md),
  [`import-wise-xlsx`](import-wise-xlsx.md)) — both formats do name a
  currency in-band; if either turns out not to, extend this helper then,
  with a real fixture first.
- Converting amounts between currencies, or warning when the filename
  currency contradicts an in-content currency.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_import_filename_metadata.py -q`
- `grep -q "def parse_wise_filename" src/kaleta/services/import_profiles.py`
- `uv run pytest tests/unit/services/test_wise_qif_import.py -q`
- `uv run pytest tests/unit/services/test_import_profiles.py -q`
- `grep -q "KAL-CSV-023" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `[manual]` Upload the real JPY QIF from `test_data/` onto a PLN account
  and confirm the import is blocked with the currency-mismatch message;
  then onto a JPY account and confirm it imports.
- `[manual]` Rename that file to `foo.qif` and confirm it still imports
  onto a JPY account (unknown currency must not block).

## Touchpoints

- `src/kaleta/services/import_profiles.py` — `parse_wise_filename`
- `src/kaleta/services/import_service.py` — `parse_queued_file(..., filename=)`,
  `_parse_wise_qif`, `WiseQifPreprocessor.extract_metadata`
- `src/kaleta/views/import_view/page.py` — pass `queued_file.filename`
  at both `parse_queued_file` call sites
- `docs/bdd.md` — update `KAL-CSV-022`, add `KAL-CSV-023`
- `tests/unit/services/test_import_filename_metadata.py` — new
- `tests/e2e/test_csv_import.py` — the QIF test's banner assertion flips
  from "no JPY" to "JPY"
- No new i18n keys — `import.currency_mismatch_block` already exists

## Open questions

- **Filename or an explicit UI field?** Default: **filename**. It is
  zero-friction and correct for every unmodified Wise download. An
  "unknown currency — please confirm" step would cover renamed files too,
  but it puts a prompt in front of every QIF import to fix a rare case.
  Revisit only if renamed uploads turn out to be common.
- **Should an unknown currency block instead of pass?** Default: **pass**.
  Blocking would make a renamed file unimportable with no way forward,
  which is worse than the status quo. The manual criteria pin both halves.
- **Trust the filename over the content if they disagree?** Default:
  **no** — content wins, filename fills only what is missing. A
  contradiction is a follow-up (warn, do not block).
- Wise's `<account_id>` segment is an opaque number and must not be
  stored or logged — it identifies the user's wallet.

## Depends on

- [`import-wise-qif`](archive/import-wise-qif.md) merged — this plan closes the
  gap that plan documented and deliberately left open.

## Implementation notes

_Filled in as work progresses._
