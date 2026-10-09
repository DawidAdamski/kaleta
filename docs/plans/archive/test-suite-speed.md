---
plan_id: test-suite-speed
title: Tests — parallel locally, tiered in CI, and an audit of what they cost
area: tests / ci
effort: medium
status: archived
archived_at: 2026-10-10
roadmap_ref: ../../roadmap.md
---

# Tests — parallel locally, tiered in CI, and an audit of what they cost

## Intent

The unit + integration suite is 3 219 tests and runs **serially**: 130 s
on the maintainer's laptop (M5 Max, 18 cores, one of them busy), and on
GitHub it runs **twice** — once on SQLite (`test`, ≈ 3.5 min) and once on
Postgres (`postgres`, ≈ 5.5 min) — before a PR can merge (measured on
`main` at `ee7e52c`, 2026-10-09). No single test is the culprit (the
slowest is 3.9 s); it is volume, per-test setup and the duplicate run.
Make the full suite a sub-30-second habit on the laptop, keep CI as the
merge gate but fast, and move the genuinely slow tier off the per-PR path.
Measure first, so the selection is evidence, not taste.

This plan lands **before** [`postgres-only`](../postgres-only.md) and is
written so that plan only has to delete the SQLite half.

## Scope

### 1. Parallel runs

- Add `pytest-xdist` to the dev group. `uv run pytest -n auto` must pass
  for `tests/unit` and `tests/integration` on both backends.
- SQLite in-memory engines are already per-test. For Postgres, each xdist
  worker gets its own database (`<db>_<worker id>`, created and migrated on
  first use from the configured `KALETA_DB_URL`, kept for the next run —
  see Implementation notes); the
  existing truncate-once + outer-transaction isolation stays per worker.
- Tests that provision tenant schemas or run Alembic (`tenancy_helpers`,
  `test_tenant_isolation`, `test_hosted_operations`, migration tests) work
  in their worker's database. Shared fixtures whose setup costs > 1 s per
  test (`test_tenant_isolation` setup is 1.4–1.9 s each) move to module
  or session scope where isolation allows it — each change justified in
  Implementation notes.
- e2e stays serial by default (one app instance on port 8081); if
  `-n` is given, each worker gets port `8081 + worker index` and its own
  database. Not required for acceptance.

### 2. Tiers

- A `slow` marker for tests ≥ 1 s on the laptop that exercise CLIs,
  subprocesses or performance budgets (the 50 000-transaction search
  budget, `reset_demo`, seed CLIs, `encrypt_database`, hosted
  operations). Marked from the measured `--durations` list, not by guess.
- `scripts/verify.sh` runs everything — the fast tier in parallel
  (`-n auto`), the slow tier serially (it holds a timing budget) — the
  laptop is where the full suite lives.
- The pre-push hook runs `pytest -n auto -m "not slow"` on unit +
  integration (target < 30 s), after mypy and import-linter.
- CI on a pull request: lint job unchanged; one test job per backend runs
  `-n auto -m "not slow"`. The slow tier and the e2e auth-against-Valkey
  job run on push to `main` and nightly (`schedule`), not per PR.
  `postgres` and `postgres-multi` merge into one job (the multi tests are
  a subset of the same suite).
- No test is skipped, deleted, xfailed or loosened to reach a target
  (Working Agreement §4). Moving a test to a later tier is not deleting it.

### 3. Audit

- `scripts/test_cost_report.py`: runs the suite with `--durations=0`
  (or reads a saved report) and writes a table — per file: test count,
  total time, setup share — to `docs/plans/test-suite-speed.md` →
  Implementation notes, plus the top 30 tests.
- From the report, list candidates for the maintainer, without acting on
  them: near-duplicate tests (same service call, same assertion shape,
  different literal), tests of code that `postgres-only` will delete
  (SQLite pragmas, SQLite backups, `encrypt_database`, desktop mode), and
  fixtures worth sharing. Deleting tests is the maintainer's call, in a
  later commit, not this plan's.

### Not in scope

- Removing SQLite or its tests (`postgres-only`).
- Rewriting e2e tests or changing what they cover.
- Changing coverage targets or the spec-coverage rules.

## Acceptance criteria

- `uv run pytest tests/unit tests/integration -n auto -q`
- `uv run pytest tests/unit tests/integration -n auto -q -m "not slow"`
- `uv run pytest tests/unit tests/integration -n auto -q -m slow`
- `grep -q "pytest-xdist" pyproject.toml`
- `grep -q '"not slow"' .pre-commit-config.yaml`
- `grep -q "schedule:" .github/workflows/ci.yml`
- `uv run python scripts/test_cost_report.py --help`
- `./scripts/verify.sh`
- `[manual]` Laptop: `time uv run pytest tests/unit tests/integration -n auto -q -m "not slow"` under 30 s; numbers before/after in Implementation notes.
- `[manual]` The first PR after merge: CI wall-clock before/after in Implementation notes.

## Touchpoints

`pyproject.toml` (dev group, `markers`), `tests/conftest.py`,
`tests/tenancy_helpers.py`, `tests/integration/conftest.py`,
`tests/e2e/conftest.py`, slow-marked test files,
`.pre-commit-config.yaml`, `.github/workflows/ci.yml`,
`scripts/verify.sh`, `scripts/test_cost_report.py` (new),
`AGENTS.md` (Commands), `docs/goal-mode.md` if the Stop hook's command
changes.

## Open questions

- Does the goal-mode Stop hook (`scripts/review_gate.sh`, plan runner)
  call `verify.sh` or pytest directly? It must pick up `-n auto` too.
  Default: through `verify.sh`.
- Some tests may share global state (`key_ring`, `settings`
  monkeypatches, files under `~/.kaleta`). Each worker gets its own
  `HOME` under `tmp_path_factory` if any such leak shows up.

## Implementation notes

**Measurements (2026-10-09, M5 Max, 18 cores; `main` at `ee7e52c` → this branch).**

| Run | Before | After |
|---|---:|---:|
| unit + integration, SQLite, serial | 130.7 s | — |
| fast tier, SQLite, `-n auto` | — | **16.8 s** |
| fast tier, Postgres 16, `-n auto` | — | **14.9 s** |
| slow tier (24 tests), serial | — | 26–29 s |
| e2e (227 tests, serial, unchanged) | 401 s | 401 s |
| CI wall-clock, pull request (#191, run 37995925370) | ≈ 5.5 min (`postgres`; `test` ≈ 3.5 min) | **2 min 15 s** (`postgres`; `test` 1 min 33 s, `lint` 23 s) |

Parallelism alone gave 130 → 29 s; the audit's first finding gave the rest.

**Decisions a reviewer should know.**

- *Worker databases are kept, not dropped.* `tests/xdist_postgres.py` creates
  `<db>_gw<N>` on first use and the worker migrates it to head
  (`upgrade_to_head`); the next session truncates it like the main one. Only
  the first parallel run pays for `CREATE DATABASE` + migrations. The plan
  said "dropped at session end"; keeping them is faster and leaves nothing a
  rerun cannot reuse. `conftest.py` sets the worker URL through
  `os.environ.update(worker_database_env())` before any `kaleta` import,
  because the settings read `KALETA_DB_URL` at import time.
- *Argon2 cost in tests.* `MfaService` and `AuthService` build a default
  `PasswordHasher()` (t=3, 64 MiB); every MFA enrolment hashes ten recovery
  codes. An autouse fixture swaps in a `PasswordHasher` with the cost the KDF
  tests already use (`_FAST_KDF`: t=1, 8 MiB). Same hash format, same verify
  path; `test_mfa_service.py` went 22.0 → 5.1 s. Production parameters are
  untouched and still asserted where they matter (`KdfParams()` defaults in
  `tests/unit/crypto/test_keys.py`). Test-only change; no `src/` file touched.
- *One order-dependent test found by xdist.* `test_health_without_credentials`
  passed serially only because an earlier test left `AsyncSessionFactory`
  configured; the API client fixtures now override `get_public_session` too.
- *`slow` tier* = 24 tests, chosen from `--durations` by the plan's rule
  (subprocess CLIs, migrations of a file database, a timing budget):
  `test_example_data`, `test_hosted_operations`, `test_reset_demo`,
  `test_encrypt_database_script`, `test_transaction_search_budget` (whole
  files), `TestEnsureSchemaCurrent`, `test_upgrading_keeps_every_balance_the_user_saw`,
  `test_recommended_activate_persists_config`. The search budget failed
  (339 ms > 300 ms) under `-n auto` with e2e running beside it — the reason
  the slow tier runs serially in `verify.sh` and CI.
- *CI*: `postgres-multi` folded into `postgres` (it now installs `hosted`, so
  the tenant suites run there); required checks `lint`, `test`, `postgres`
  keep their names (ruleset "protect the queen"). Pull requests run the fast
  tier; push to `main`, the nightly schedule and `workflow_dispatch` add the
  slow tier and the `valkey` job.
- *Not moved to module scope*: `test_tenant_isolation` setup (76 % of its
  8.6 s). Each test provisions two fresh tenants on purpose — sharing them
  would let one test's rows leak into the next one's isolation check, which
  is the property under test. Under xdist it costs one worker ~9 s.

**Accepted risk: what a pull request no longer runs.** Until push to `main`
(or the nightly run), a PR is not checked by the slow tier — tenant
migrations and the operator CLI (`test_hosted_operations`), `reset_demo`,
the seed CLIs (`test_example_data`), `encrypt_database`, Alembic upgrades of
a file database (`TestEnsureSchemaCurrent`, KAL-ACC-009's balance-preserving
upgrade, first-run activation), the 50 000-row search budget — nor by the
`valkey` job. A migration, CLI or Redis-path regression can therefore merge
and be caught only after. Mitigation: `verify.sh` (the Definition-of-Done
gate and the goal-mode Stop hook) runs the slow tier, so an agent or a human
following the Working Agreement has run it before opening the PR. `valkey`
is not a required check (the ruleset requires `lint`, `test`, `postgres`),
so its being skipped on a PR blocks nothing.

**Also recorded after review.**

- No test exercises Argon2 at production cost; with the autouse fixture
  none can by accident. `kaleta.auth.providers.fake` still hashes at full
  cost — left alone, `postgres-only` removes that backend.
- `tests/xdist_postgres.py` needs a role with `CREATEDB` (CI's `kaleta` is a
  superuser), builds the asyncpg DSN with `make_url` (any `postgresql*`
  driver, no SQLAlchemy query options leak), refuses a URL without a
  database name, and tolerates a concurrent `CREATE DATABASE`. Two pytest
  sessions at once on the same server share the worker databases and
  truncate each other — documented in the module; run one at a time.

**Audit — candidates for the maintainer (nothing below was changed).**

1. *e2e MFA test, 76.6 s of 401 s*: `tests/e2e/test_mfa.py::test_two_factor_authentication`
   waits for real TOTP windows. Generating codes for an explicit
   `for_time` (or a clock the app reads) would cut ~70 s.
2. *Tests of code `postgres-only` deletes*: `tests/unit/db/test_sqlite_pragmas.py`,
   `tests/integration/test_sqlite_integrity_backups.py`, `test_backup.py`,
   `tests/unit/services/test_scheduled_backup_service.py`, the SQLite parts of
   `test_integrity_service.py`, `test_migrate_on_startup.py` (safety copy),
   `test_encrypt_database_script.py`, `TestSyncUrl::test_sqlite_drops_async_driver`
   — 11 of them already skip on Postgres.
3. *Setup-heavy integration files* (59–86 % setup: `test_payees`,
   `test_transactions`, `test_institutions`, `test_categories`,
   `test_accounts`, `test_budgets`): each test creates the API user and a
   bearer token. A module-scoped user with per-test rollback would halve them;
   worth doing only if they grow.
4. *Seeder registry tests* (`tests/unit/seeders/test_registry.py`, 8.1 s, 17
   tests) seed the whole dataset several times; `test_example_data.py`
   (slow tier) covers the same seeding through the CLI. Overlap to review:
   `TestSeedAll::test_replace_rewrites_without_growing` vs
   `test_replace_rewrites_the_dataset_with_foreign_keys_enforced`.
5. No near-duplicate unit tests were identified with confidence from timings
   alone; a coverage-diff pass (`--cov-context=test`) would be the tool if
   the maintainer wants one.

Post-fix cost report (Postgres, serial, `scripts/test_cost_report.py --top 15`):
107 s summed over 3 185 tests — top files `test_hosted_operations` 9.4 s,
`test_tenant_isolation` 8.6 s, `test_registry` 8.1 s, `test_example_data` 7.9 s,
`test_mfa_service` 5.1 s.

## Implementation (filled by plan-archiver)

## Implementation

Landed on 2026-10-10.

| SHA | Author | Date | Message |
|---|---|---|---|
| `b6927b1` | Dawid (Ani) | 2026-10-09 | test(api): API client fixtures override the registry session too |
| `9ed3fa0` | Dawid (Ani) | 2026-10-09 | test: run the suite in parallel — pytest-xdist, a PostgreSQL database per worker, test-cost Argon2 |
| `f11487c` | Dawid (Ani) | 2026-10-09 | ci: fast tier per pull request, slow tier on main and nightly |
| `114b126` | Dawid (Ani) | 2026-10-09 | docs(plans): test-suite-speed measurements and audit; test_cost_report.py |
| `46139a5` | Dawid (Ani) | 2026-10-09 | test: harden worker databases after review; record the PR-path risk |
| `5093d29` | Dawid (Ani) | 2026-10-09 | docs(plans): test-suite-speed CI wall-clock after the change |

**Files changed:**
- .github/workflows/ci.yml
- .pre-commit-config.yaml
- AGENTS.md
- docs/deployment.md
- docs/plans/test-suite-speed.md
- pyproject.toml
- scripts/test_cost_report.py
- scripts/verify.sh
- tests/conftest.py
- tests/integration/conftest.py
- tests/integration/test_account_balances.py
- tests/integration/test_encrypt_database_script.py
- tests/integration/test_example_data.py
- tests/integration/test_first_run.py
- tests/integration/test_hosted_operations.py
- tests/integration/test_reset_demo.py
- tests/integration/test_tenant_isolation.py
- tests/unit/services/test_setup_service.py
- tests/unit/services/test_transaction_search_budget.py
- tests/xdist_postgres.py
- uv.lock

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `uv run pytest tests/unit tests/integration -n auto -q` | 0 |
| `uv run pytest tests/unit tests/integration -n auto -q -m "not slow"` | 0 |
| `uv run pytest tests/unit tests/integration -n auto -q -m slow` | 0 |
| `grep -q "pytest-xdist" pyproject.toml` | 0 |
| `grep -q '"not slow"' .pre-commit-config.yaml` | 0 |
| `grep -q "schedule:" .github/workflows/ci.yml` | 0 |
| `uv run python scripts/test_cost_report.py --help` | 0 |
| `./scripts/verify.sh` | 0 |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
