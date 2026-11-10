---
plan_id: import-remember-mapping-pattern
title: "Remember this mapping" must not suggest a pattern that matches every account
area: import
effort: small
status: archived
archived_at: 2026-11-10
roadmap_ref: ../../roadmap.md
---

# "Remember this mapping" must not suggest a pattern that matches every account

## Intent

mBank names statement exports `<last 8 digits of account>_<yymmdd from>_<yymmdd to>.csv`,
e.g. `78886836_261011_261109.csv`. The settings step pre-fills "Filename pattern"
with `ImportRuleService.suggest_filename_pattern`
(`src/kaleta/services/import_rule_service.py:177`), which replaces the **first**
digit block with `*`. For these names it removes the account digits and keeps
the dates: `*_261011_261109.csv`.

"Remember this mapping" defaults to on (`QueuedFile.remember_mapping = True`,
`src/kaleta/views/import_view/state.py:53`). Saved as suggested, the rule matches
every statement downloaded for the same period and sends it to the account
chosen for the first file. On 2026-11-09 the box had to be unticked on all 8 files.

A second problem surfaced in review: `ImportRuleService.create` logs the pattern
(`import_rule_service.py:67`, `pattern=%r`). A pattern that keeps account digits
would put account-number digits in plain-text logs, against ADR-35 (the operator
cannot see account numbers).

## Scope

In scope:

1. **Recognise mBank statement names by position**, not by guessing which digit
   blocks are dates: `^(\d{8})_(\d{6})_(\d{6})\.csv$` (case-insensitive) →
   `\1_*_*.csv`. Every other name keeps today's behaviour (first digit block → `*`;
   `mbank-2025-10.csv` → `mbank-*.csv`).
2. **Never suggest or save a pattern made only of wildcards and separators**
   (e.g. `*_*_*.csv`, `*.csv`): `suggest_filename_pattern` returns `""` for such
   results, and `ImportRuleService.create` refuses them with a `ValidationError`.
3. **Remember defaults to off when the account was matched by number.** In
   `handle_upload` (`page.py:~464`), after `_auto_match_account` returns `True`, set
   `queued_file.remember_mapping = False`. Put the decision in a pure function
   (`default_remember_mapping(auto_matched: bool) -> bool`) with a unit test, and
   check `inherit_queue_settings` does not copy `True` back from the previous file.
4. **No pattern in logs.** Drop `pattern=%r` from the `create` log line (keep id
   and account id).

Tests (`tests/unit/services/test_import_rule_service.py::TestSuggestFilenamePattern`
unless noted):

- `test_mbank_statement_name_keeps_account_digits`: `78886836_261011_261109.csv` → `78886836_*_*.csv`
- `test_wildcard_only_pattern_is_not_suggested`: `2025-10-01_2025-10-31.csv` → `""`
- existing three cases unchanged
- `test_create_refuses_wildcard_only_pattern` (service)
- `test_create_log_has_no_pattern` (caplog)
- `test_default_remember_mapping_off_when_auto_matched` (pure function)
- e2e `tests/e2e/test_import_remember_default.py`: upload an mBank statement for a
  registered account → the box is unticked and the pattern keeps the account digits.

Out of scope:

- Cleaning up rules already saved with a bad pattern. Old bad patterns match only
  one statement period, and account auto-match already overrides a rule's account
  (`page.py:~464`); mention "Manage saved mappings" in the release note.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_import_rule_service.py -q`
- `uv run pytest tests/unit -q -k default_remember_mapping`
- `uv run pytest tests/e2e/test_import_remember_default.py -q`
- `grep -c "KAL-CSV-041" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

## Touchpoints

- `src/kaleta/services/import_rule_service.py` — `suggest_filename_pattern`, `create` (log line + validation)
- `src/kaleta/views/import_view/page.py` — `handle_upload` default after auto-match
- `src/kaleta/views/import_view/state.py` — `QueuedFile.remember_mapping` (unchanged default; set per file)
- `src/kaleta/services/import_service.py` — `inherit_queue_settings` (check only)
- tests above; `docs/bdd.md` — `KAL-CSV-041` next to `KAL-CSV-016`
- i18n: refusal message for a wildcard-only pattern (en/pl)

## Open questions

None. Decided: older history exports like `dawid72288564_000101_261013.csv` do
not match the statement regex and keep today's behaviour (`dawid*_000101_261013.csv`).

## Implementation notes

- **Inconsistency in the plan, resolved.** Scope item 1 keeps today's rule for
  every non-statement name (first digit block → `*`), which turns
  `2025-10-01_2025-10-31.csv` into `*_2025-10-31.csv`. That pattern is not made
  only of wildcards and separators, yet the plan's test expects `""` for that
  name. Following the plan's intent (never suggest a pattern that names nothing
  but a period), the two checks are kept apart:
  - `is_wildcard_only(pattern)`: true when, after removing the extension,
    wildcards (`*`, `?`) and separators (`_`, `-`, `.`, whitespace), nothing is
    left. It is used to refuse a save, exactly as the plan states.
  - `suggest_filename_pattern` additionally returns `""` when that remainder
    has no letter, i.e. the suggestion names only digits and dates.
  So `mbank-2025-10.csv` → `mbank-*.csv`, `statement.csv` → `statement.csv`,
  and the decided `dawid72288564_000101_261013.csv` →
  `dawid*_000101_261013.csv` are unchanged, while
  `2025-10-01_2025-10-31.csv`, `12345.csv` and an empty name give `""` (an
  empty name used to give `*`).
- **mBank statement names.** `^(\d{8})_(\d{6})_(\d{6})(\.csv)$`,
  case-insensitive, becomes `<8 digits>_*_*<extension as written>`
  (`.CSV` stays `.CSV`).
- **Refusal sits in `_normalise_pattern`.** That covers `create` as the plan
  asks, and also `update` and `upsert_from_import`, which save through the same
  normaliser ("never … save"). It raises `ValidationError` with
  `errors.import_rule.pattern_matches_everything` (en/pl, minimal JSON diff).
  From the import page, a remembered rule that cannot be saved still surfaces
  through the existing `import.rule_save_failed` toast.
- **Remember default.** `default_remember_mapping(auto_matched)` lives next to
  `inherit_queue_settings` in `import_service.py`. `handle_upload` sets
  `remember_mapping` from it right after `_auto_match_account`. Inheritance
  cannot copy `True` back: `QueueSettingsSnapshot` has no remember field, and
  a unit test pins that.
- **Log.** `Created import rule id=%s account_id=%s`; caplog test asserts that
  the account digits never appear. (`RuleService.create` for categorisation
  rules also logs its pattern; those patterns are merchant text, not account
  numbers, so they are out of scope here.)
- **Tests.** Unit tests are in `tests/unit/services/test_import_rule_service.py`
  (on `main`'s `src/` they cannot even import `default_remember_mapping`).
  KAL-CSV-041 is covered by `tests/e2e/test_import_remember_default.py` with a
  new statement fixture `44440393_261011_261109.csv` for its own account
  number. On `main`'s `src/` the e2e test fails: the box is ticked.

## Implementation (filled by plan-archiver)

## Implementation

Landed on 2026-11-10 (PR #408).

| SHA | Author | Date | Message |
|---|---|---|---|
| `324c7788` | Dawid Adamski | 2026-11-10 | Merge pull request #408 from DawidAdamski/plan/import-remember-mapping-pattern |

**Files changed:**
- docs/bdd.md
- docs/plans/import-remember-mapping-pattern.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/services/import_rule_service.py
- src/kaleta/services/import_service.py
- src/kaleta/views/import_view/page.py
- tests/e2e/fixtures/import/44440393_261011_261109.csv
- tests/e2e/test_import_remember_default.py
- tests/unit/services/test_import_rule_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Still @planned in docs/bdd.md: KAL-CSV-016 — retag before or after archiving.
