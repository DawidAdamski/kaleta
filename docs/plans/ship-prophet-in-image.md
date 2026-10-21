---
plan_id: ship-prophet-in-image
title: Ship Prophet in the default container image
area: deploy
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Ship Prophet in the default container image

## Intent
The default container image (`Containerfile`) is built with
`uv sync --frozen --no-dev`, which omits the optional `forecast` extra, so
Prophet is absent from the shipped image. Account-balance forecasting then
silently falls back to the naive "simple projection" path
(`is_prophet_available()` returns False). The maintainer wants the DEFAULT
image to include Prophet so Prophet-backed forecasting works out of the box.

## Scope
- Add `--extra forecast` to BOTH `uv sync` invocations in `Containerfile`
  (the `--no-install-project` layer-cache step and the project step).
- Keep everything else intact: `python:3.13-slim` base, non-root `app` user,
  `HOME=/home/app`, `KALETA_VERSION` build arg, `UV_NO_SYNC=1`.
- Prove the image builds and Prophet imports + `is_prophet_available()` is
  True inside it.

Explicitly NOT in scope:
- Regenerating `uv.lock` (it already resolves prophet + cmdstanpy + holidays).
- Any application-behaviour change — the app already degrades gracefully with
  or without Prophet; this only changes what the image ships.

## Acceptance criteria
- `podman build -t kaleta-prophet-test -f Containerfile .` succeeds.
- `podman run --rm kaleta-prophet-test uv run python -c "import prophet; from kaleta.services.forecasters import is_prophet_available; print('PROPHET_OK', is_prophet_available())"`
  prints `PROPHET_OK True`.

## Touchpoints
- `Containerfile`

## Open questions
- Does prophet ship a cp313 wheel (no compiler needed at build time), or must
  it build from source (needs a C/C++ toolchain / multi-stage split)? Resolved
  during the build — see Implementation notes.

## Implementation notes
- BDD (Working Agreement rule 5): no `KAL-*` scenario added. This is a
  packaging change; there is no user-facing app behaviour that pytest/e2e can
  assert, because the app already behaves correctly with and without Prophet.
  Acceptance is the image build + in-image import check above.
- `uv.lock` already contains `prophet`, `cmdstanpy` and `holidays` (dev
  installs `--extra forecast`), so `uv sync --frozen --extra forecast`
  resolves without touching the lock.
