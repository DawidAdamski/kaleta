---
plan_id: import-filename-currency-guard
title: Import — currency guard for statements that carry no currency
area: import
effort: medium
status: archived
archived_at: 2026-09-09
roadmap_ref: ../../roadmap.md#import
---

# Import — currency guard for statements that carry no currency

## Intent

The currency-mismatch guard in `validate_import_readiness` stops a user
importing a JPY statement onto a PLN account. It works by comparing
`metadata.currency` against the target account's currency — and it only
fires when the file names its currency.

**A Wise QIF never does.** Confirmed against a real export
([`import-wise-qif`](import-wise-qif.md), *Fixture provenance*): the body
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
- MT940 / XLSX ([`import-wise-mt940`](../import-wise-mt940.md),
  [`import-wise-xlsx`](../import-wise-xlsx.md)) — both formats do name a
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

- [`import-wise-qif`](import-wise-qif.md) merged — this plan closes the
  gap that plan documented and deliberately left open.

## Implementation notes

### Open questions — all four defaults taken

- **Filename, not a UI field.** `parse_wise_filename` reads the download
  name; no confirmation step was added.
- **Unknown passes.** A name that does not match the Wise shape yields
  `None`, the currency stays `""`, and `validate_import_readiness`
  already skips its block on a falsy currency — so nothing changed for a
  renamed upload. `KAL-CSV-024` pins that half in e2e, so a future
  "fail closed" refactor breaks a test rather than a user's import.
- **Content wins.** The name is read only inside
  `WiseQifPreprocessor.extract_metadata`, the one path whose format
  names no currency. The mBank and Wise-CSV branches never consult it,
  so a contradiction between name and content cannot arise yet.
- **The account id is discarded.** `_WISE_FILENAME` matches the
  `<account_id>` segment with a bare `\d+` and never captures it, and
  `WiseFilenameMetadata` has no field for it —
  `test_the_result_holds_currency_and_period_only` asserts the field set
  so a future field cannot smuggle it in.

### Decisions taken while implementing

- **One view call site, not two.** The plan expected two
  `parse_queued_file` calls in `import_view/page.py`; there is one, in
  the `_parse_file` helper that every parse and re-parse routes through.
  Nothing else in `src/` calls it.
- **The fixture keeps its name; tests choose one per upload.** Renaming
  `jpy-travel-sample.qif` to a Wise shape would have baked the currency
  into the fixture and left no way to exercise the renamed-upload path
  without a second copy of the same bytes. Instead `_upload_as()` feeds
  the fixture's bytes to the widget under whatever name the test needs
  (Playwright's `FilePayload` form of `set_input_files`). Both halves of
  the guard are covered by the one fixture.
- **The wallet id is anonymized in the repo.** The real
  `<account_id>` appears in the archived QIF plan's provenance table;
  it is not propagated further. Tests, the regex comment and NOTES.md
  use `12345678`, matching the fixtures' existing anonymization
  convention.
- **Two scenarios, not one.** The plan asked for "a new scenario for the
  block itself". The block and the must-not-block halves have different
  Givens and different outcomes, so they are `KAL-CSV-023` (JPY name
  onto a PLN account is blocked) and `KAL-CSV-024` (renamed upload stays
  unknown and imports). `KAL-CSV-022`'s "banner shows no currency" line
  became "shows currency JPY, read from the download name", plus a line
  pinning that the period stays the one the rows cover.
- **The period assertion is now two-sided.** `extract_metadata` parses
  the name's dates and deliberately ignores them, which is invisible in
  a test that only checks the right answer. The e2e also asserts the
  banner contains neither `2026-04-01` nor `2026-06-30` — the name's
  requested range — so a future change that starts trusting the name
  fails loudly.

### Finding, not fixed here (out of scope)

`SettingsSection._update_currency_warning`
(`src/kaleta/views/import_view/settings_section.py`) calls
`currency_mismatch_warning` without the falsy-currency guard that
`validate_import_readiness` has. When a file's currency is unknown it
compares `"" != "PLN"` and shows *"File currency () differs from account
currency (PLN)"* — an empty-parens warning on a file that is perfectly
importable. This predates the plan and is unchanged by it (a QIF's
currency was `""` for every upload before; now it is `""` only for
unrecognised names, so the change makes it strictly rarer). Fixing it
means touching the warning path, which this plan's scope does not
cover — filed on the Chore inbox
([#20](https://github.com/DawidAdamski/kaleta/issues/20)) instead.

## Implementation

Landed on 2026-09-09 (PR #83).

| SHA | Author | Date | Message |
|---|---|---|---|
| `0040357` | Dawid Adamski | 2026-09-09 | Merge pull request #83 from DawidAdamski/plan/import-filename-currency-guard |

**Files changed:**
- docs/bdd.md
- docs/plans/import-filename-currency-guard.md
- src/kaleta/services/import_profiles.py
- src/kaleta/services/import_service.py
- src/kaleta/views/import_view/page.py
- tests/e2e/fixtures/import/wise/NOTES.md
- tests/e2e/test_csv_import.py
- tests/unit/services/test_import_filename_metadata.py
- tests/unit/services/test_wise_qif_import.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
