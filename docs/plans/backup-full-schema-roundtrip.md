---
plan_id: backup-full-schema-roundtrip
title: Backup covers every ORM table + alembic revision stamp
area: settings / data
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Backup covers every ORM table + alembic revision stamp

## Intent

Settings → Data → Export/Restore currently dumps only 8 of ~25 tables.
A restore silently drops payees, tags, subscriptions, loans, plans, users,
and more — and can leave a hybrid DB (old orphan rows + restored ledger).
Backups also lack an alembic revision stamp, so schema drift is invisible.

## Scope

- Derive the export/restore table list from `Base.metadata.sorted_tables`
  (register any missing models in `kaleta.models` so metadata is complete).
- Stamp the current alembic head revision into `metadata.json`.
- Refuse restore when `alembic_revision` is missing or mismatches the
  running head (no silent column dropping; "migrate backup" is out of scope).
- Fail with `ValidationError` when a backup row contains unknown columns.
- Round-trip unit test: seed every model, export, wipe, restore, equal counts.
- BDD: retag/extend KAL-SET-014/015; add mismatch scenario.

### Not in scope

- Migrating an older backup forward to the current schema.
- Changing the ZIP layout beyond `metadata.json` fields and full table set.
- UI redesign of the Data tab.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_backup_service.py -q`
- `./scripts/verify.sh`
- `grep -E 'KAL-SET-01[456]' docs/bdd.md | grep -q '@automated'`

## Touchpoints

- `src/kaleta/services/backup_service.py`
- `src/kaleta/models/__init__.py` (Institution, CurrencyRate registration)
- `tests/unit/services/test_backup_service.py`
- `docs/bdd.md` (KAL-SET-014…016)

## Open questions

- None — refuse-on-mismatch is the chosen default; migrate-backup later.

## Implementation notes

- Table list is `Base.metadata.sorted_tables` after registering `Institution`
  and `CurrencyRate` in `kaleta.models` (they were missing from the package
  `__init__`, so metadata was incomplete).
- `alembic_revision` is the ScriptDirectory head (code schema), not the DB
  `alembic_version` row — works for in-memory test DBs that use `create_all`.
- Unknown columns raise `ValidationError`; missing columns still insert as
  NULL/default (DB enforces NOT NULL).
- Spec coverage only scans e2e/integration, so BDD `Covers:` live in
  `tests/integration/test_backup.py`; the comprehensive round-trip stays in
  `tests/unit/services/test_backup_service.py` as requested.
- PostgreSQL: do not `suppress` a failed `PRAGMA foreign_keys` — asyncpg
  aborts the transaction and subsequent DELETEs fail. Gate PRAGMA on
  `dialect.name == "sqlite"` instead. Seed `AuditLog.timestamp` as naive
  datetime to match `DateTime()` (no tz) columns.
- Restore deserializes JSON scalars via ORM column types (`Date` /
  `DateTime` / `Numeric`) before INSERT — asyncpg rejects ISO date/time
  strings and needs real `date`/`datetime`/`Decimal` values.
