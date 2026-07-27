---
plan_id: migrate-on-startup
title: Auto-migrate configured DB on app start (schema drift after git pull)
area: setup / ops
effort: small
status: archived
archived_at: 2026-07-27
roadmap_ref: ../roadmap.md#cross-cutting-principles
source: ../plans/audit-production-readiness.md#4-migrations-dont-run-on-upgrade--schema-drift-after-git-pull
---

# Auto-migrate configured DB on app start

## Intent

After `git pull` brings new Alembic revisions, a returning user’s
configured database (`~/.kaleta/config.json`) must be brought to head
before the app serves traffic. Today migrations run only on first
activation via the setup wizard, so upgrades leave the live schema
stale and the first query that touches a new column fails at runtime.

## Scope

- In `_preload_config()`, after rebinding the engine from config, ensure
  the configured DB’s alembic revision matches head.
- When the DB is behind head:
  - **SQLite file DB:** take a pre-migration `VACUUM INTO` safety copy
    via `ScheduledBackupService` (same `KALETA_BACKUP_DIR` as finding 2),
    then `alembic upgrade head`.
  - **Non-SQLite:** upgrade with a clear log warning (no automatic dump).
- When the DB is already at head: no-op.
- When the DB is ahead of the installed code (unknown revision), or
  upgrade fails: refuse to start with a clear message that names
  current vs head and points at the safety copy / manual
  `KALETA_MIGRATE_URL=… uv run alembic upgrade head` path.
- Share the sync upgrade path used by `activate_database` so first-run
  and return-run use one implementation.
- Update README quick start and getting-started so they no longer imply
  that bare `uv run alembic upgrade head` migrates the live configured
  DB; document `KALETA_MIGRATE_URL` for manual runs.
- BDD scenario `KAL-SET-019` + unit/integration tests.

### Not in scope

- Scheduled / retained `VACUUM INTO` backups (audit finding 2).
- SQLite integrity pragmas (finding 3).
- `/health` pending-migration flag (finding 9).
- Zero-config first-run rewrite (`setup-zero-config-bootstrap`) beyond
  what auto-migrate enables for the README line.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_setup_service.py tests/integration/test_migrate_on_startup.py -q`
- `grep -q 'KAL-SET-019' docs/bdd.md`
- `grep -q 'KALETA_MIGRATE_URL' README.md`
- `grep -q 'KALETA_MIGRATE_URL' docs/getting-started.md`
- `./scripts/verify.sh`
- `[manual]` Starting the app against a configured SQLite DB stamped at
  an older revision upgrades it and writes a `kaleta-*.db` under
  `KALETA_BACKUP_DIR` before migrating.

## Touchpoints

- `src/kaleta/services/setup_service.py` — revision compare, safety copy,
  sync upgrade, `ensure_schema_current`
- `src/kaleta/main.py` — call from `_preload_config`
- `src/kaleta/exceptions.py` — typed startup/migration error if needed
- `README.md`, `docs/getting-started.md`
- `docs/bdd.md` — `KAL-OPS-001`
- `tests/unit/services/test_setup_service.py`

## Open questions

- None — auto-upgrade with SQLite safety copy (not refuse-only) matches
  the audit’s preferred path for a local daily driver.

## Implementation notes

- Reused `ScheduledBackupService.create_backup()` for the pre-migration
  safety copy (same `KALETA_BACKUP_DIR` / retain settings as audit finding 2)
  rather than a sibling `*.pre-migrate-*.db` beside the live file.
- Sync path in `ensure_schema_current`; `run_migrations` / `activate_database`
  share `upgrade_to_head`. `_preload_config` calls ensure and exits via
  `SystemExit` on `MigrationError`.
- Unknown DB revision (ahead of / foreign to installed scripts) refuses
  before any upgrade attempt; no safety copy in that case.

## Implementation

Landed on 2026-07-26.

| SHA | Author | Date | Message |
|---|---|---|---|
| `33bcfd8` | Dawid (Ani) | 2026-07-26 | fix: auto-migrate configured DB on app start |

**Files changed:**
- `src/kaleta/services/setup_service.py`
- `src/kaleta/services/__init__.py`, `src/kaleta/exceptions.py`
- `src/kaleta/main.py`
- `README.md`, `docs/getting-started.md`
- `docs/bdd.md`
- `tests/unit/services/test_setup_service.py`
- `tests/integration/test_migrate_on_startup.py` (new)

**Acceptance criteria run** (step 3b):

| Command | Exit |
|---|---|
| `uv run pytest tests/unit/services/test_setup_service.py tests/integration/test_migrate_on_startup.py -q` | 0 |
| `grep -q 'KAL-SET-019' docs/bdd.md` | 0 |
| `grep -q 'KALETA_MIGRATE_URL' README.md` | 0 |
| `grep -q 'KALETA_MIGRATE_URL' docs/getting-started.md` | 0 |
| `./scripts/verify.sh` | 0 |
