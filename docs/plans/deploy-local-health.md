---
plan_id: deploy-local-health
title: Local deploy docs + unauthenticated health + NiceGUI storage pin
area: ops / api
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
source: ../plans/audit-production-readiness.md#9-local-deployment-story-no-autostart-no-health-endpoint
---

# Local deploy docs + unauthenticated health + NiceGUI storage pin

## Intent

Make Kaleta a true daily-driver on a laptop: document launchd/systemd
autostart for localhost web mode, expose an unauthenticated health probe
(version, DB reachability, pending-migration flag), and stop NiceGUI
session files from accumulating in the repo working directory.

## Scope

- New `docs/deploy-local.md` with launchd plist + systemd unit examples
  (`KALETA_MODE=web`, `KALETA_HOST=127.0.0.1`, pinned WorkingDirectory).
- Unauthenticated `GET /api/v1/health` (optional `/health` alias) returning
  app version, DB reachability, and a pending-migration flag.
- Pin NiceGUI storage under `~/.kaleta/` via `NICEGUI_STORAGE_PATH` and
  sweep stale storage files older than 30 days on startup.
- BDD scenario under Public API + unit test `tests/unit/api/test_health.py`.
- Link from README.

### Not in scope

- Docker / Compose changes.
- Auto-migrate implementation (only *report* pending migrations; startup
  migrate is covered by `migrate-on-startup`).
- Settings UI for storage path or health knobs.
- Auth / rate-limiting for the health endpoint (must stay public).

## Acceptance criteria

- `uv run pytest tests/unit/api/test_health.py tests/integration/test_health.py -q`
- `grep -q 'KAL-API-004' docs/bdd.md`
- `test -f docs/deploy-local.md`
- `grep -q 'deploy-local' README.md`
- `grep -qE 'launchd|systemd' docs/deploy-local.md`
- `grep -q '/api/v1/health' docs/deploy-local.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh`

## Touchpoints

- `docs/deploy-local.md` (new), `README.md`
- `src/kaleta/services/health_service.py` (new)
- `src/kaleta/services/nicegui_storage_service.py` (new)
- `src/kaleta/schemas/health.py` (new)
- `src/kaleta/api/v1/health.py` (new)
- `src/kaleta/api/__init__.py`, `src/kaleta/main.py`
- `src/kaleta/auth/middleware.py` — public `/health`
- `docs/bdd.md` — `KAL-API-004`
- `tests/unit/api/test_health.py`, `tests/integration/test_health.py`

## Open questions

- None — report-only pending-migration flag; storage under
  `~/.kaleta/nicegui`; 30-day mtime sweep matches NiceGUI’s default tab TTL.

## Implementation notes

- Plan file was missing from the tree; created from audit finding 9 + the
  agent task brief before implementation.
- Health is mounted on a **public** `/api/v1` router sibling so it does not
  inherit `require_api_auth` from the authenticated `v1_router`.
  `/health` alias registered via `register_health_alias` on NiceGUI and
  headless FastAPI apps; auth middleware lists `/health` as a public UI path.
- `migrations_pending` is report-only (`current_revision` vs `head_revision`);
  no migrate call from the probe. Revision readout errors are treated as
  pending so monitors notice drift.
- NiceGUI storage: `NICEGUI_STORAGE_PATH` setdefault to `~/.kaleta/nicegui`
  in `kaleta/__init__.py` and again (stdlib-only) at the top of `main.py`
  before `nicegui` import — `Storage.path` is class-level at import time.
  `NiceguiStorageService.sweep_stale()` deletes regular files with mtime
  older than 30 days on web/app startup and api lifespan.
- Spec coverage only scans `tests/integration/` + `tests/e2e/`; added a thin
  integration test alongside the required `tests/unit/api/test_health.py`.
- `pyproject.toml` per-file ignore `E402` on `main.py` for the pre-import
  storage pin block.
