---
plan_id: backup-scheduler-active-db-url
title: Scheduled backups must target the active database from config.json
area: settings
effort: small
status: archived
archived_at: 2026-08-11
roadmap_ref: ../../roadmap.md#settings
---

# Scheduled backups must target the active database

## Intent

The backup scheduler backs up the database from **environment settings**
(`KALETA_DB_URL`, default `~/.kaleta/kaleta.db`) instead of the **active
database** configured via the setup wizard in `~/.kaleta/config.json`.
When those differ, every scheduled backup either fails or — worse —
silently backs up the *wrong* database while the user believes their real
data is protected. This is a hole in the P0 data-safety layer
(see [`audit-production-readiness.md`](audit-production-readiness.md), finding 2).

Observed in the wild (config.json pointed at a non-default path; app ran
fine, migration safety copy was written correctly, then):

```
ERROR [kaleta.services.backup_scheduler] Scheduled backup failed
kaleta.exceptions.ValidationError: SQLite database file not found: /Users/…/.kaleta/kaleta.db
```

## Root cause

- `ScheduledBackupService.from_settings()` reads `settings.db_url`
  (pydantic env settings) — but the app's live engine is reconfigured at
  startup from `setup_config.get_db_url()` (`~/.kaleta/config.json`),
  which takes precedence in `main._preload_config()`.
- `BackupScheduler._loop()` constructs the service **once** before the
  loop, so even a correct URL would go stale after the user ejects and
  activates a different database via `/setup`.
- The migration-time safety copy is unaffected (it receives the real URL
  explicitly from `setup_service`), which is why the two log lines in the
  repro disagree.

## Scope

- Add `ScheduledBackupService.from_active_config()` that resolves the URL
  with the same precedence as `main._preload_config()`:
  `setup_config.get_db_url() or settings.db_url`. Backup dir/retention
  still come from settings.
- `BackupScheduler._loop()`: build the service **inside each iteration**
  (cheap — it only resolves paths), so a DB switch via `/setup` is picked
  up on the next tick without a process restart.
- On database activation (`setup_service.activate_database()`): trigger
  one immediate `run_once()` (or restart the scheduler) so a freshly
  activated database gets a first snapshot right away.
- Audit remaining `from_settings()` call sites for the same mismatch
  (`grep -rn "from_settings" src/`) — anything that means "the user's
  active database" must resolve via `setup_config` first.
- **BDD**: add `KAL-SET-023 @planned` to `docs/bdd.md` (Feature:
  Settings — Data safety) — scheduled backup snapshots the database
  configured in config.json, not the environment default. Retag once the
  unit test lands.

Out of scope: backup UI, retention policy changes, PostgreSQL backups
(scheduler correctly skips non-SQLite URLs today).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_scheduled_backup_service.py -q`
- `grep -q "KAL-SET-023" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` Repro from the log: activate a DB at a non-default path via
  the setup wizard, start the app with default `KALETA_DB_URL`, and
  confirm the first scheduled backup writes a snapshot of the *active*
  database (matching filename in the backup dir, no ValidationError in
  the log).

## Touchpoints

- `src/kaleta/services/scheduled_backup_service.py`
  (`from_active_config`, keep `from_settings` for tests or remove)
- `src/kaleta/services/backup_scheduler.py` (`_loop`)
- `src/kaleta/services/setup_service.py` (post-activation snapshot)
- `docs/bdd.md` (KAL-SET-023)
- `tests/unit/services/test_scheduled_backup_service.py`

## Open questions

1. Should `run_once()` failures on N consecutive ticks surface in the UI
   (Settings → Data banner) instead of log-only? Default: log-only in
   this plan; a visibility follow-up can ride with the observability plan
   ([`observability-anonymous-events.md`](observability-anonymous-events.md)).

## Implementation notes

- Only `backup_scheduler.py` called `from_settings()` for the live DB URL;
  kept `from_settings` for env-only / test construction, added
  `from_active_config` for the active-DB precedence used by the scheduler.
- `activate_database` takes a post-activation `run_once()` snapshot with the
  activated URL (not via the scheduler task) so a fresh DB is protected even
  when the interval has not yet elapsed; failures are logged, not raised.
- Open question 1 (UI surfacing of consecutive failures): deferred per plan
  default (log-only).

## Implementation

Landed on 2026-08-11. PR [#49](https://github.com/dadamski/kaleta/pull/49).

| SHA | Author | Date | Message |
|---|---|---|---|
| `0c5f027` | Dawid Adamski | 2026-08-11 | fix(backup): snapshot the active DB from config.json (#49) |

**Files changed:**
- docs/bdd.md
- docs/plans/backup-scheduler-active-db-url.md
- src/kaleta/services/backup_scheduler.py
- src/kaleta/services/scheduled_backup_service.py
- src/kaleta/services/setup_service.py
- tests/integration/test_first_run.py
- tests/integration/test_sqlite_integrity_backups.py
- tests/unit/services/test_scheduled_backup_service.py

**Acceptance criteria run** (step 3b):

| Command | Exit |
|---|---|
| `uv run pytest tests/unit/services/test_scheduled_backup_service.py -q` | 0 |
| `grep -q "KAL-SET-023" docs/bdd.md` | 0 |
| `uv run python scripts/spec_coverage.py` | 0 |
| `bash scripts/verify.sh` | 0 |
