---
plan_id: q3-engineering-hygiene
title: Engineering hygiene — exceptions, logging, CI
area: infrastructure
effort: medium
status: draft
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Engineering hygiene — exceptions, logging, CI

## Intent

Three cross-cutting gaps before the repo can go public: services raise
bare `ValueError`s (views can't distinguish user error from bug),
logging is minimal, and nothing runs automatically on push. Small
individually, together they define contributor experience.

## Scope

- **Exceptions:** `src/kaleta/exceptions.py` with a hierarchy —
  `KaletaError` → `NotFoundError`, `ValidationError`,
  `ConflictError`, `ImportError_` (CSV), `ForecastUnavailableError`.
  Services raise these instead of bare `ValueError`/`RuntimeError`.
  One shared handler maps them: views → toast (`ui.notify`, negative);
  API → HTTP status (404/422/409/503) with a JSON error envelope.
  Migrate services incrementally — start with transaction, budget,
  import services.
- **Logging:** module-level loggers (`logging.getLogger(__name__)`),
  app-level config in `main.py` honouring `KALETA_DEBUG`; request
  logging middleware in API mode; warnings for fallback paths (e.g.
  Prophet missing). No `print()` left in `src/`.
- **CI (GitHub Actions):** on PR + push to main:
  `ruff check` + `ruff format --check`, `mypy src/`,
  `pytest tests/unit tests/integration` (with coverage report),
  e2e smoke job (boot app + run 1-2 fastest Playwright scenarios).
  Cache uv. Badge in README.
- **Draft-plan triage:** close or fold the cosmetic drafts
  (`*-color-fix`, `dashboard-chart-fluid-height`) into
  `q3-views-refactor`; move remaining feature drafts under a
  `## Q4 candidates` note in their frontmatter (`status: draft`,
  add `deferred_to: q4-2026`).
- **Not in scope:** error monitoring (Sentry), metrics, release
  automation, docs publishing (Q4).

## Acceptance criteria

- `grep -rn "raise ValueError" src/kaleta/services/` → zero hits in
  migrated services; new pattern documented in `CLAUDE.md`.
- API error responses share one envelope: `{"error": {"code", "message"}}`.
- `grep -rn "print(" src/kaleta/` → zero hits.
- CI green on a fresh PR; failure in any job blocks merge.
- `docs/plans/` contains no stale cosmetic drafts.

## Touchpoints

`src/kaleta/exceptions.py` (new), all of `src/kaleta/services/`
(incremental), `src/kaleta/api/` (error handler), `views/` (toast
mapping helper), `main.py`, `.github/workflows/ci.yml` (new),
`CLAUDE.md`, `docs/plans/*`.

## Open questions

- Does the audit log (`db/audit.py`) also capture handled domain
  exceptions, or only mutations? (Suggest: mutations + auth only.)

## Implementation notes

- Exception hierarchy in `src/kaleta/exceptions.py`; handlers in
  `kaleta.api.errors` and `kaleta.views.error_handling`.
- All services migrated off bare `ValueError`/`RuntimeError`.
- API envelope unified to `{"error": {"code", "message"}}` including auth 401.
- `KALETA_API_TOKEN`: minimum 16 chars, constant-time compare via
  `secrets.compare_digest`.
- Logging: `configure_logging()` in `main.py`, request middleware in API mode,
  Prophet fallback warning in `forecasters`.
- Cosmetic drafts folded into archived `q3-views-refactor`; feature drafts
  tagged `deferred_to: q4-2026`.
