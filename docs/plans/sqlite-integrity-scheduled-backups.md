---
plan_id: sqlite-integrity-scheduled-backups
title: SQLite integrity pragmas + scheduled VACUUM backups
area: db / housekeeping / settings
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# SQLite integrity pragmas + scheduled VACUUM backups

## Intent

Daily-driver durability for the default SQLite deployment: enforce foreign
keys and WAL at every connection, surface orphan rows in Housekeeping, and
keep rolling on-disk file backups via `VACUUM INTO` with retention.

## Scope

- Connect-time SQLite pragmas (`foreign_keys=ON`, `journal_mode=WAL`,
  `busy_timeout=5000`, `synchronous=NORMAL`) on engine create/reconfigure
- `PRAGMA foreign_key_check` via `IntegrityService` + Housekeeping Integrity card
- Scheduled file backups: on process start, then every N hours; keep last K;
  configurable directory via env
- Env settings (`KALETA_BACKUP_*`), BDD, unit/integration tests, docs
  (`getting-started`, `tech-stack`, `AGENTS` env block)

### Not in scope

- Fixing JSON ZIP completeness (separate plan; mitigated for SQLite by VACUUM)
- Settings UI for backup knobs
- Cloud upload / encryption / restore-from-VACUUM UI
- Postgres scheduling (no-op when dialect is not SQLite)

## Acceptance criteria

- `uv run pytest tests/unit/db/ tests/unit/services/test_scheduled_backup_service.py tests/unit/services/test_integrity_service.py -q`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `grep -E 'KAL-SET-01[7-9]|KAL-INT-' docs/bdd.md | grep -q .`

## Touchpoints

- `src/kaleta/db/session.py`
- `src/kaleta/config/settings.py`
- `src/kaleta/services/scheduled_backup_service.py` (new)
- `src/kaleta/services/backup_scheduler.py` (new)
- `src/kaleta/services/integrity_service.py` (new)
- `src/kaleta/views/housekeeping.py`
- `src/kaleta/main.py`
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/bdd.md`, `docs/getting-started.md`, `docs/tech-stack.md`, `AGENTS.md`
- `tests/unit/db/`, `tests/unit/services/`, `tests/integration/`

## Open questions

- None locked — defaults: `backup_enabled=true`, interval 24h, retain 7,
  dir `~/.kaleta/backups`; env-only; one branch for pragmas + backups.

## Implementation notes

- Connect pragmas registered on `engine.sync_engine` via SQLAlchemy
  `connect` listeners inside `_SessionProxy._init` (re-registered on every
  `configure()` / new engine).
- Scheduled backups use a sibling `ScheduledBackupService` (not ZIP
  `BackupService`): open the live SQLite file with stdlib `sqlite3` and
  `VACUUM INTO` — avoids aiosqlite transaction quirks; works under WAL
  with concurrent readers.
- `BackupScheduler` is an idempotent asyncio task started from NiceGUI
  `on_startup` (web/app) and FastAPI `lifespan` (api). No-op when
  disabled, non-SQLite, or `:memory:`.
- Backups are SQLite file snapshots (`kaleta-YYYYMMDD-HHMMSS.db`), not the
  Settings ZIP format; restore-from-VACUUM UI is out of scope.
- Spec coverage requires 3–4 letter area codes (`KAL-HK` is invalid);
  integrity scenarios use `KAL-INT-001` / `KAL-INT-002`.
- Spec coverage requires `Covers:` in `tests/integration/` (unit tests
  also carry the IDs for local readability).
- Housekeeping Integrity card is read-only; SQLite-only messaging when
  dialect is not SQLite.
