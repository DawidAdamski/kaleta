---
plan_id: alembic-drift-reconcile
title: Reconcile Alembic model/DB drift
area: db / migrations
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Reconcile Alembic model/DB drift

## Intent
`uv run alembic check` on a freshly migration-built database was red: a
cluster of model-vs-DB drift that predates the models it names (an index on
`gifts`, two on `import_runs`, the `fk_categories_parent_id` delete behaviour,
and seven timestamp columns typed `timestamp` vs `timestamptz`). Autogenerate
noise makes every future migration review harder and hides real drift. Make
`alembic check` clean on a fresh head DB with the **models as the source of
truth**, via one migration plus model declarations.

## Scope
Covers, and only covers, the drift `alembic check` reports at head
`d4f7a9c2e1b6`:

- **Indexes present in DB, absent from models.**
  - `ix_import_runs_account_id`, `ix_import_runs_created_at` — **keep**:
    declare them on `ImportRun` (`__table_args__`). They already exist in the
    DB, so declaring removes the drift with no migration op. Both are real
    query predicates (`account_service` windows by `account_id`;
    `import_service` lists newest-first by `created_at`).
  - `ix_gifts_user_id` — **drop** in the migration. `gifts` are listed per
    family schema and fetched by `id`; `user_id` is never a predicate, and no
    other `UserOwnedMixin` table indexes it.
- **`fk_categories_parent_id`** — migration alters the FK to
  `ON DELETE SET NULL` to match `Category.parent_id`.
- **Timestamps** — migration `ALTER COLUMN ... TYPE`, reconciling toward the
  model each way:
  - `currency_rates.{created_at,updated_at}`, `saved_reports.{created_at,updated_at}`,
    `tags.{created_at,updated_at}`: `timestamp` → `timestamptz`
    (`TimestampMixin` declares `DateTime(timezone=True)`).
  - `reserve_funds.archived_at`: `timestamptz` → `timestamp without time zone`
    (the model declares a plain `DateTime()`).

**Not in scope:** `ix_categorisation_rules_pattern` and
`ix_import_rules_filename_pattern` — the field-encryption revision
(`r2s3t4u5v6w7`) drops them on purpose (an index on ciphertext is useless), and
the models correctly omit them. They are **not** drift and are not touched. The
`alembic_public/` registry is separate and is not involved.

## Acceptance criteria

- `KALETA_DEBUG=true uv run alembic upgrade head` (fresh DB) then
  `KALETA_DEBUG=true uv run alembic check` prints `No new upgrade operations detected.`
- `KALETA_DEBUG=true uv run alembic downgrade -1 && KALETA_DEBUG=true uv run alembic upgrade head` round-trips clean
- `KALETA_DEBUG=true uv run alembic heads` shows a single head
- `uv run ruff check . && uv run ruff format --check . && uv run mypy src/`
- `uv run lint-imports`
- `uv run pytest tests/unit tests/integration -n 2 -m "not slow"`
- `uv run python scripts/spec_coverage.py`

No user-facing behaviour changes, so no new BDD scenario (Working Agreement §5).

## Touchpoints
- `src/kaleta/models/import_run.py` — declare the two kept indexes.
- `alembic/versions/9f318d21f98a_reconcile_model_db_drift_fk_ondelete_.py` — new
  migration (`down_revision = d4f7a9c2e1b6`): FK `SET NULL`; timestamp type
  alters; drop `ix_gifts_user_id`.
- `docs/plans/chores.md` — tick the two drift chores.

## Open questions / assumptions

- **Timestamp conversion is non-shifting because every stored value is UTC
  (confirmed, not assumed).** The `ALTER ... USING col AT TIME ZONE 'UTC'`
  clause reinterprets a naive value as UTC (forward) or renders a `timestamptz`
  as its UTC wall clock (reverse). That is correct **iff** the stored values are
  UTC. Evidence gathered on the test DB:
  - Session `TimeZone` is `UTC` (`SHOW timezone` / `current_setting('timezone')`);
    the app sets none, so it inherits the server default.
  - ORM writes bind `TimestampMixin`'s `DateTime(timezone=True)` columns as
    `timestamptz` (default `datetime.now(UTC)`, aware). Inserting an aware-UTC
    value (as `timestamptz`) into a naive column stored the UTC wall clock
    exactly; `now()` did the same; `col AT TIME ZONE 'UTC'` read back the correct
    instant.
  - `reserve_funds.archived_at` is written as
    `datetime.now(UTC).replace(tzinfo=None)` (naive UTC) by `ReserveFundService`.
  - The explicit `AT TIME ZONE 'UTC'` makes the conversion deterministic
    regardless of the session `TimeZone` in force when the migration runs — it
    does not rely on the migration connection being UTC. **If a deployment ever
    stored these columns as local (non-UTC) wall clock, this migration would
    mislabel them; no evidence of that exists in this codebase.**
- **`fk_categories_parent_id` → `ON DELETE SET NULL`** is the maintainer's chosen
  delete behaviour (the model already declares it); the migration aligns the DB
  to it.
- **`reserve_funds.archived_at` reconciles toward the model** (plain
  `DateTime()` = `timestamp without time zone`), the reverse direction of the
  original chore note. The service writes naive UTC, consistent with a naive
  column.

## Implementation notes
- Revision `9f318d21f98a`, `down_revision = d4f7a9c2e1b6` (the head reported by
  `alembic heads`). Single head after.
- The migration hard-codes no schema: a per-family run is rewritten by
  `schema_translate_map` in `alembic/env.py`, exactly as every other migration
  (ADR-35/ADR-38, PostgreSQL only — no dialect branches).
- `alembic check` confirmed clean on a fresh head DB; upgrade → downgrade →
  upgrade round-trips clean.

## Implementation (filled by plan-archiver)
