---
plan_id: import-currency-warning-empty
title: Import currency warning suppressed for unknown file currency
area: import
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Import currency warning suppressed for unknown file currency

## Intent
When an imported file carries no currency, the import settings section shows a
spurious warning — `File currency () differs from account currency (PLN)` —
because `currency_mismatch_warning` compares an empty string against the
account currency and finds them unequal. The sibling guard
`validate_import_readiness` already skips the mismatch block when either
currency is falsy. Align the warning helper with that behaviour.

## Scope
- `src/kaleta/services/import_service.py`: `currency_mismatch_warning` returns
  `False` unless both currencies are present, keeping the `.upper()`
  comparison.
- **Not in scope:** any view change. `views/import_view/settings_section.py`
  already delegates to the helper, so it is deliberately untouched — this keeps
  the change a non-view diff (short verify gate, no e2e).

## Acceptance criteria
- `uv run pytest tests/integration/test_import_currency_warning.py -q`
- `uv run python scripts/spec_coverage.py`
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`

## Touchpoints
- `src/kaleta/services/import_service.py`
- `tests/integration/test_import_currency_warning.py` (new)
- `docs/bdd.md` (KAL-CSV-038)

## Open questions
- Should whitespace-only currencies count as empty? Resolved: no — the
  readiness guard uses a plain truthiness check, so the warning helper mirrors
  it with a simple `bool()` guard.

## Implementation notes
- Fix mirrors `validate_import_readiness` exactly (truthiness, not strip), so
  both code paths agree on what "unknown currency" means.
- Covering test lives in `tests/integration` because `scripts/spec_coverage.py`
  scans integration + e2e only, not unit. The pre-existing unit test
  `tests/unit/services/test_import_service.py::TestCurrencyMismatchWarning`
  stays as-is.
