# Settings validation error must not leak secrets

status: in-progress
owner: Dawid (Ani)
issue: chore (docs/plans/chores.md ~line 371, from plan/hosted-tenancy-foundation)

## Intent

When `Settings()` fails validation at startup, pydantic's `ValidationError`
carries each offending field's raw `input` value. For settings these inputs
come from the environment / `.env`, so the error can echo the start of
`KALETA_SECRET_KEY` (or any other secret) onto stderr or into logs. Report
such a failure by message only: the offending field name(s) plus the error
summary and type, never the input values.

## Findings (current state)

- `src/kaleta/config/settings.py` already sets `hide_input_in_errors=True`
  (commit bda90e6), which masks the raw value from `str(exc)` and from the
  default traceback. Verified empirically.
- However `exc.errors()[i]["input"]` STILL contains the raw value even with
  that flag set. Any code that logs or reprs `.errors()` would leak it, and
  the flag is a non-obvious safety net rather than a guarantee at the
  construction site.
- `settings = Settings()` runs at module import (line 323). On failure the
  bare `pydantic.ValidationError` propagates uncaught — a startup crash.

## Scope

- ONLY the settings construction / error-reporting path in
  `src/kaleta/config/settings.py`.
- Add one unit test under `tests/unit/config/`.

## Not in scope

- No migration, no model changes (other lane owns those).
- Do not change WHICH settings are valid or WHEN construction fails — only
  WHAT is printed on failure.
- The existing per-field validators and their messages are unchanged.

## Approach

- Add `load_settings()` that calls `Settings()` and, on
  `pydantic.ValidationError`, re-raises `kaleta.exceptions.ValidationError`
  with a message built only from each error's `loc`, `msg`, and `type`
  (never `input` or `ctx`), using `raise ... from None` so the chained
  pydantic exception (and its `input`) cannot reach a traceback.
- `settings = load_settings()` at module level (keeps the same
  fail-at-import behaviour, only the exception type and message change).
- `Settings()` / `Settings.model_validate()` remain usable directly; existing
  tests that assert `pydantic.ValidationError` keep working.

## Acceptance

- `load_settings()` raises `kaleta.exceptions.ValidationError` on invalid
  settings; the message names the offending field and never contains the
  secret value.
- Unit test with a literal sentinel secret in env proves the field is named
  and the sentinel substring is absent from the raised message.
- `ruff check`, `ruff format --check`, `mypy src/`, `lint-imports`,
  `pytest -m "not slow"`, `spec_coverage.py` all green.

## BDD

No user-facing screen change (startup robustness / secret hygiene). There is
no existing KAL-SET scenario about startup error rendering, and inventing one
for an internal stderr/log concern would not map onto a Feature a user drives
(rule 5). Rationale recorded here; no new KAL scenario added.

## Touchpoints

- `src/kaleta/config/settings.py` (construction + new `load_settings` helper)
- `tests/unit/config/test_settings_error_no_secret_leak.py` (new)
- `docs/plans/chores.md` (tick the chore)

## Implementation notes

- `hide_input_in_errors=True` masks `str(exc)` but NOT `exc.errors()[i]["input"]`
  — the wrapper is the real guarantee, built from loc/msg/type.
- Message built from `loc`/`msg`/`type` only; for custom validators pydantic's
  `msg` is "Value error, <our text>" and never contains the submitted value.
