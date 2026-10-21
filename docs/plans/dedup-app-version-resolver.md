---
plan_id: dedup-app-version-resolver
title: Dedup the app-version resolver in the view layer
area: views
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Dedup the app-version resolver in the view layer

## Intent
Two view helpers read the installed package version independently, each
with its own `importlib.metadata.version('kaleta')` call and its own
`"v0.1.0"` offline fallback. There is already one canonical resolver,
`kaleta.observability.app_version()` (the bug-report dialog uses it).
Point both view helpers at that single resolver so the version string
has one source of truth in the view layer.

## Scope
- `src/kaleta/views/layout.py` — `_APP_VERSION` module constant (drawer
  foot).
- `src/kaleta/views/auth_common.py` — `app_version()` helper (auth foot).

Explicitly **not** in scope:
- `src/kaleta/__init__.py` (`__version__` / `_resolve_version`). The
  chore lists it as a third copy, but the canonical resolver already
  reads `kaleta.__version__`, so `__init__` is the root of the single
  source of truth, not a duplicate to collapse into itself. Touching it
  would ripple beyond the two view helpers.
- Any change to the rendered label in the normal (installed) case.

## Observed version formats (the CRITICAL check)
- `kaleta.observability.app_version()` returns a **bare** version string
  (no leading `v`) — it returns `kaleta.__version__`, which is
  `importlib.metadata.version('kaleta')`. Offline/not-installed fallback
  is `"0.0.0+unknown"` (from `_resolve_version`), or `"unknown"` if the
  attribute read itself raised.
- Both view helpers currently render a **`v`-prefixed** string:
  `f"v{_pkg_version('kaleta')}"`, with a `"v0.1.0"` offline fallback.
- Installed version at time of writing: `0.7.1.dev155+gb5b867d29`, so the
  app actually renders `v0.7.1.dev155+gb5b867d29`. `v0.1.0` is a
  never-hit offline constant (the package is always installed at
  runtime).

### Decision
Call `kaleta.observability.app_version()` and keep the `v`-prefix at the
view call site: `f"v{app_version()}"`. In the installed case this is
byte-identical to the previous output (same bare version, same `v`
prefix). The two `"v0.1.0"` fallbacks are removed per the chore; the
offline fallback now consolidates to the canonical resolver's
(`v0.0.0+unknown`). This fallback path is not reachable in a running
deployment, so the user-visible label is unchanged.

## Acceptance criteria
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run pytest tests/unit/observability/test_version.py -q`
- `uv run python scripts/spec_coverage.py`

## Touchpoints
- `src/kaleta/views/layout.py`
- `src/kaleta/views/auth_common.py`

## Implementation notes
- `kaleta.observability.app_version` is a legal import from the view
  layer (import-linter permits `views -> kaleta.observability`; the
  bug-report dialog already imports it). Confirmed `lint-imports` green.
- `auth_common.app_version()` is kept as a thin public wrapper (it is
  called internally at the auth foot). Removed the now-dead
  `importlib.metadata` imports (`PackageNotFoundError`, `version`) from
  both files.
- Behaviour-preserving refactor: no new BDD scenario (Working Agreement
  rule 5 N/A).
