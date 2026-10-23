---
plan_id: errors-i18n-message-keys
title: Domain errors carry a translation key, so toasts speak the user's language
area: cross-cutting
effort: large
status: draft
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Domain errors carry a translation key, so toasts speak the user's language

## Intent
A Polish user who hits a handled domain error reads it in English.
`notify_kaleta_error` (`src/kaleta/views/error_handling.py:178`,
`_notify_with_event`) toasts `exc.message` verbatim, and services build that
message as an English free-text string at the `raise` site — e.g.
`payee_service.py:314` raises
`ConflictError(f"'{pattern}' is already an identity of payee '{owner_name}'")`.
With payee-identity conflicts and merge-undo now common, English error toasts
are a routine part of the Polish UX.

## Why this is a shape change, not a lookup table
The chore inbox line ("map error codes to `t()` keys") understates it. Two
facts make a flat `code → t()` map impossible:

1. **`code` is too coarse.** `KaletaError.code` is one of a handful of
   buckets (`conflict`, `validation_error`, `not_found`, …; see
   `src/kaleta/exceptions.py`). Dozens of distinct user-facing messages share
   a single code, so the code cannot select the right sentence.
2. **Messages carry interpolated runtime data** (payee names, patterns,
   amounts). A bare key cannot reproduce
   `'{pattern}' is already an identity of payee '{owner_name}'` — the view
   needs the *parameters*, not just a key.

There are ~252 `raise` sites of `KaletaError` subclasses across
`src/kaleta/services/*.py` (44 of them interpolated f-strings). Localizing
them is a cross-cutting contract change, hence a plan rather than a chore
line.

## Scope
Covers:
- Give `KaletaError` an **optional** structured carrier for localization:
  a `message_key: str | None` and `params: dict[str, object]` (names TBD in
  Open questions), set via keyword at the `raise` site, e.g.
  `raise ConflictError(message_key="errors.payee.identity_taken",
  params={"pattern": pattern, "owner": owner_name})`. The positional
  `message` stays as the English fallback and as what logs/`event_capture`
  and the API currently read.
- `notify_kaleta_error` / `_notify_with_event`: when `message_key` is set,
  render the toast via `t(message_key, **params)`; otherwise fall back to
  `exc.message` (today's behaviour), so un-migrated raises keep working.
- Add the `errors.*` key namespace to `en.json` and `pl.json`.
- **Migrate the user-facing raise sites incrementally**, highest-traffic
  first. This plan ships the carrier + the error_handling wiring + the first
  cohort (payee identity / payee merge-undo, the ones named in the chore).
  The remaining services get their own follow-up slices referencing this
  plan — do NOT attempt all 252 in one PR (rule 9: single-purpose diffs).
- API error responses (`kaleta.api.errors`) keep emitting the English
  `message` under `{"error": {"code", "message"}}`; localizing the API is
  explicitly out of scope here (clients negotiate language differently).

Does NOT cover:
- Changing `code` values or the API error contract.
- A full sweep of all 252 raise sites (follow-up slices).
- Server-side locale negotiation for the REST API.

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-" docs/bdd.md` (new scenario for the localized toast)
- `uv run pytest tests/integration -k "error_i18n or notify_kaleta" -n 2 -m "not slow"`
- `./scripts/verify.sh --e2e` (error_handling is a view → rule 8)
- `[manual]` A Polish session sees the payee-identity-conflict toast in
  Polish, with the payee name interpolated correctly.

## Touchpoints
- `src/kaleta/exceptions.py` — add `message_key` / `params` to `KaletaError.__init__`.
- `src/kaleta/views/error_handling.py` — `_notify_with_event` resolves the key.
- `src/kaleta/services/payee_service.py` (`:314`), `payee_merge_service.py` —
  first cohort of migrated raises.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — `errors.*` namespace.
- `docs/bdd.md` — new `KAL-ERR-NNN` scenario; `tests/integration` or
  `tests/e2e` cover it.

## Open questions
- Field names: `message_key` + `params`, or a single `localized:
  tuple[str, dict] | None`? Prefer two explicit fields for mypy clarity.
- Do we assert at construction that every `params` placeholder exists in the
  key's template? A test that loads both locales and checks the first-cohort
  keys format without `KeyError` is cheaper than a runtime guard.
- Pluralization: none of the first-cohort messages pluralize; defer ICU-style
  plural handling until a message needs it.

## Implementation notes
- Keep `message` (English) as the stored/logged/`event_capture` string —
  observability and the API already read it; only the *toast* localizes.
- The fallback path (no `message_key`) is what makes the migration
  incremental and keeps the diff single-purpose per slice.
