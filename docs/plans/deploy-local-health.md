---
plan_id: deploy-local-health
title: Local deploy docs, /health endpoint, NiceGUI storage GC
area: ops / api / docs
effort: small
status: draft
roadmap_ref: ../roadmap.md#cross-cutting-principles
source: audit-production-readiness.md#9-local-deployment-story-no-autostart-no-health-endpoint
---

# Local deploy docs, /health endpoint, NiceGUI storage GC

## Intent

Daily run currently means a terminal window: no launchd/systemd
examples, no health probe for uptime monitors, and NiceGUI session
storage (`.nicegui/`) accumulates in the CWD (repo root). Ship a
local deployment guide, a trivial unauthenticated health route, and
pin + sweep session storage so a background local instance is
practical.

## Scope

- New [`docs/deploy-local.md`](../deploy-local.md):
  - macOS **launchd** plist example:
    `KALETA_MODE=web`, `KALETA_HOST=127.0.0.1`, pinned
    `WorkingDirectory` (e.g. `~/.kaleta/run` or data dir — not the
    git checkout), `ProgramArguments` via `uv run kaleta`
  - Linux **systemd** user/system unit with the same env
  - Pointer to interim runbook in
    [`audit-production-readiness.md`](audit-production-readiness.md)
    until P0 backups/migrations land
- Health route (prefer `/api/v1/health` or top-level `/health` —
  pick one and document): unauthenticated JSON with
  - app version
  - DB reachability (simple `SELECT 1`)
  - pending-migration flag (alembic current vs head) — dovetails
    with audit P0.4 auto-migrate work
- NiceGUI storage:
  - Pin storage directory under `~/.kaleta/` (or the launchd
    WorkingDirectory), not the repo CWD
  - Startup sweep of stale session files (age threshold, e.g.
    >30 days) so GC is automatic
- Unit/API test for health shape; docs link from README
  getting-started

### Not in scope

- Docker / Podman (see ADR-006)
- Authenticated admin health with secrets
- Full observability / metrics stack
- Implementing auto-migrate itself (P0.4 / separate plan) — health
  only **reports** pending migrations

## Acceptance criteria

- `test -f docs/deploy-local.md`
- `grep -E 'launchd|systemd' docs/deploy-local.md | grep -q .`
- `uv run pytest tests/unit/api/test_health.py -q`
- `grep -E 'KAL-API-.*health|/health' docs/bdd.md | grep -q .`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh`
- `[manual]` `curl -s http://127.0.0.1:8080/api/v1/health` (or
  chosen path) returns JSON with version + db ok while app runs.

## Touchpoints

- `docs/deploy-local.md` (new)
- `docs/` examples or snippets for plist / unit (inline in doc or
  `docs/deploy/`)
- `src/kaleta/api/` — health router
- `src/kaleta/main.py` — storage path + GC + register route
- `src/kaleta/config/settings.py` — storage dir if needed
- `README.md` — link to deploy-local
- `docs/bdd.md` — health scenario under Public API
- `tests/unit/api/test_health.py`

## Open questions

1. Path: `/health` vs `/api/v1/health` — default:
   **`/api/v1/health`** plus optional `/health` alias for dumb
   probes.
2. Exact stale-file age for `.nicegui` GC — default **30 days**.

## Implementation notes

_Filled in as work progresses._

Source finding: `audit-production-readiness` P1.9. One plan = one
branch = one PR. Suggested first Multitask pickup after P0 gate.
