---
plan_id: q3-forecast-optional-prophet
title: Make Prophet optional — forecast extra + lightweight fallback
area: forecast
effort: medium
status: draft
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Make Prophet optional — forecast extra + lightweight fallback

## Intent

Prophet (plus cmdstan) adds ~300 MB to every install and Docker image
for a single feature, and is imported unconditionally. For an
open-source launch the default install must stay slim; forecasting
should degrade gracefully, not crash, when Prophet is absent.

## Scope

- Move `prophet` from core dependencies to an optional extra in
  `pyproject.toml`: `uv sync --extra forecast`.
- Forecaster abstraction in the forecast service: `ProphetForecaster`
  (unchanged behaviour, incl. model presets) and `NaiveForecaster` —
  seasonal-naive or rolling-mean with a simple quantile band; both
  return the same result schema (yhat, lower, upper) so views and the
  zero-balance alert are untouched.
- Import Prophet lazily inside `ProphetForecaster`; selection at
  runtime: Prophet if importable, else fallback.
- Forecast view: when running on the fallback, show an unobtrusive
  banner "Advanced forecasting (Prophet) not installed — using simple
  projection" with a docs link; hide Prophet-only preset selector.
- Containerfile: build two images — `kaleta:slim` (default, no
  Prophet) and `kaleta:full`; docker-compose default stays `full` for
  existing users, README documents both.
- Unit tests for `NaiveForecaster` and for the selection logic
  (Prophet import mocked away).
- **Not in scope:** changing Prophet model behaviour, new forecast
  features, replacing Prophet entirely.

## Acceptance criteria

- `uv sync` (no extras) → app starts, all pages load, Forecast shows
  fallback projection + banner; zero traceback anywhere.
- `uv sync --extra forecast` → behaviour identical to today.
- `uv run pytest` green in both configurations (CI matrix later).
- Slim Docker image at least 250 MB smaller than full.

## Touchpoints

`pyproject.toml`, `uv.lock`, forecast service module(s) in
`src/kaleta/services/`, `src/kaleta/views/forecast*.py`,
`Containerfile`, `docker-compose.yml`, README,
`docs/tech-stack.md`, `tests/unit/services/`.

## Open questions

- Fallback algorithm: seasonal-naive (repeat weekly pattern) vs
  rolling 30-day mean with trend? Pick whichever scores better on the
  seed dataset — record the comparison in implementation notes.
- Does the forecast cache key need a `model=naive|prophet` component
  so switching installs doesn't serve stale curves? (Likely yes.)

## Implementation notes

(filled in as work progresses)
