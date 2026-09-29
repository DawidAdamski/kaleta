---
plan_id: deps-sqlalchemy-2-1
title: Upgrade SQLAlchemy 2.0 → 2.1
area: platform
effort: small
status: archived
archived_at: 2026-09-29
roadmap_ref: ../../roadmap.md
---

# Upgrade SQLAlchemy 2.0 → 2.1

## Intent
Dependabot PR #157 bumps `sqlalchemy` 2.0.54 → 2.1.0 in `uv.lock` and fails
CI in two jobs. `lint` fails because mypy finds 3 new errors from the
tighter 2.1 typing. `postgres` fails because 2.1 changed the default driver
for a bare `postgresql://` URL from psycopg2 to psycopg (v3), which is not
installed. This plan makes the codebase work on 2.1 so the bump can land.
The PR from this branch supersedes #157.

## Scope
- Bump `sqlalchemy` to 2.1.0 in `uv.lock`; raise the floor in
  `pyproject.toml` to `>=2.1`, because the fixes rely on 2.1 behaviour.
- Fix the mypy errors in `services/transaction_service.py` and
  `services/unplanned_radar_service.py` by design (real types, no `Any`,
  no `type: ignore`).
- `setup_service._sync_url`: map `+asyncpg` to an explicit sync driver that
  the `postgres` extra actually installs, so it no longer relies on
  SQLAlchemy's default driver.
- Unit tests that pin the `_sync_url` mapping (`TestSyncUrl` in
  `tests/unit/services/test_setup_service.py`).

Not in scope: switching the `postgres` extra from psycopg2 to psycopg 3,
adopting new 2.1 APIs, and other packages in the Dependabot group.

## Acceptance criteria
- `uv run python -c "import sqlalchemy, sys; sys.exit(0 if sqlalchemy.__version__.startswith('2.1') else 1)"`
- `uv run mypy src/`
- `uv run pytest tests/unit/services/test_setup_service.py -q -k TestSyncUrl`
- `./scripts/verify.sh`
- `[manual]` The `postgres` CI job passes on the PR.

## Touchpoints
`pyproject.toml`, `uv.lock`, `src/kaleta/services/setup_service.py`,
`src/kaleta/services/transaction_service.py`,
`src/kaleta/services/unplanned_radar_service.py`,
`tests/unit/services/test_setup_service.py`.

## Open questions
- Which sync PG driver? Default: `psycopg2`. The `postgres` extra ships
  `psycopg2-binary`, so it needs no new dependency.

## Implementation notes
- `uv lock --upgrade-package sqlalchemy` resolved **2.1.1**, not the 2.1.0
  in #157; 2.1.1 is the current patch, and the acceptance check only pins 2.1.
- Floor raised to `sqlalchemy>=2.1`: `Select[Transaction]` uses the 2.1
  variadic `Select` generic, and `_sync_url` relies on 2.1 driver naming.
- `TransactionService._base_stmt` returned `Any`, so 2.1's typed
  `Result.scalars()` could not infer `export_ledger_csv`'s list. It now
  returns `Select[Transaction]`, which fixes the cause rather than
  annotating the one variable.
- `UnplannedRadarService.planned_with_history` selected
  `Transaction.planned_transaction_id` (`int | None`) and used it as a
  dict key. It now selects `PlannedTransaction.id`, which is the same value
  under the inner join's equality and is non-null by type.
- Open question resolved with its default: `_sync_url` maps `+asyncpg` →
  `+psycopg2`. The `postgres` CI job was replayed locally against a
  `postgres:16` container (`--extra postgres`, `alembic upgrade head`,
  unit + integration): 2612 + 185 passed. The previously failing
  `test_health_service_reports_not_pending_when_at_head` now passes.
- Supersedes Dependabot PR #157 — close it once this merges.

## Implementation

Landed on 2026-09-29 (PR #163).

| SHA | Author | Date | Message |
|---|---|---|---|
| `46d1c15` | Dawid Adamski | 2026-09-29 | Merge pull request #163 from DawidAdamski/plan/deps-sqlalchemy-2-1 |

**Files changed:**
- docs/plans/chores.md
- docs/plans/deps-sqlalchemy-2-1.md
- pyproject.toml
- src/kaleta/services/setup_service.py
- src/kaleta/services/transaction_service.py
- src/kaleta/services/unplanned_radar_service.py
- tests/unit/services/test_setup_service.py
- uv.lock

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
