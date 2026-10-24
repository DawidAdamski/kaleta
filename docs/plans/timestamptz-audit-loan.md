---
plan_id: timestamptz-audit-loan
title: Make audit_log.timestamp and personal_loans.settled_at tz-aware
area: models / migrations
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#settings
---

# Make `audit_log.timestamp` and `personal_loans.settled_at` tz-aware

## Intent
`TimestampMixin` and the rest of the schema store timestamps as
`timestamptz`, but two columns are still `timestamp without time zone`:
`audit_log.timestamp` and `personal_loans.settled_at`. Their models declare
a plain `DateTime()`, and `PersonalLoanService` even strips the tzinfo
(`datetime.now(UTC).replace(tzinfo=None)`) to match the naive column. This
is the leftover `postgres-only` part B3 noted: the "SQLite hands back naive
datetimes" fallbacks were dropped only where columns are already
`timestamptz`. Bring these two in line so every stored instant carries its
zone and the strip-tzinfo workaround can go.

## Scope
Covers:
- `audit_log.timestamp` and `personal_loans.settled_at` models change from
  `DateTime()` to `DateTime(timezone=True)`.
- One Alembic migration (head `9f318d21f98a`) altering both columns to
  `timestamptz` with `USING … AT TIME ZONE 'UTC'` — non-shifting, since
  every stored value is already UTC. Follows the exact per-family pattern of
  `9f318d21f98a` (`schema_translate_map` rewrites each family run; no schema
  is hard-coded).
- Drop the `.replace(tzinfo=None)` in
  `PersonalLoanService.add_repayment` (writes aware UTC now).
- Update the `settled_at` seed value and the `AuditLog` test fixture in
  `tests/backup_helpers.py` to aware UTC (matching their tz-aware neighbours).

Explicitly NOT in scope:
- `reserve_funds.archived_at` — deliberately naive and already reconciled
  toward its plain-`DateTime()` model by `9f318d21f98a`. Left untouched.
- `TimestampMixin` and every `timestamptz` column — already correct.
- No user-facing change: the loan row still shows `settled_at.date()` (the
  same UTC date) and the audit list the same instant, so no BDD scenario —
  this is schema reconciliation like `9f318d21f98a`, not new behaviour.

## Acceptance criteria

- `uv run pytest tests/integration/test_timestamptz_audit_loan.py -q`
- `uv run pytest tests/unit/services/test_personal_loan_service.py tests/integration/test_backup.py -q`
- `grep -q "AT TIME ZONE 'UTC'" alembic/versions/*timestamptz*audit*loan*.py`
- `./scripts/verify.sh`

## Touchpoints
- `src/kaleta/models/audit_log.py` — `timestamp` → `DateTime(timezone=True)`.
- `src/kaleta/models/personal_loan.py` — `settled_at` → `DateTime(timezone=True)`.
- `src/kaleta/services/personal_loan_service.py` — drop `.replace(tzinfo=None)`.
- `src/kaleta/seeders/personal_loans.py` — aware `settled_at`.
- `tests/backup_helpers.py` — aware `AuditLog.timestamp` fixture.
- `alembic/versions/<new>_timestamptz_audit_loan.py` — the migration.
- `tests/integration/test_timestamptz_audit_loan.py` — covering test.

## Implementation notes
- **Non-shifting.** `audit_log.timestamp` is written by `func.now()` under a
  UTC session; `settled_at` was written as naive UTC. `AT TIME ZONE 'UTC'`
  therefore names the same instant each way, independent of the session
  `TimeZone` at migration time — the same argument `9f318d21f98a` makes.
- The reverse-direction (`reserve_funds.archived_at`) stays as-is: its model
  is a plain `DateTime()` and `ReserveFundService` still writes naive UTC.
- **Old backups restore cleanly.** `BackupService._coerce` (`backup_service.py:139`)
  keeps whatever tzinfo the ISO string carried for a `timezone=True` column; a
  pre-change backup holds these two columns as naive UTC strings, which asyncpg
  stores into `timestamptz` as the same UTC instant. Non-shifting, the same as
  every other `timestamptz` column already restored this way.
