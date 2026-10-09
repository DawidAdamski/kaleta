---
plan_id: test-suite-speed
title: Tests — parallel locally, tiered in CI, and an audit of what they cost
area: tests / ci
effort: medium
status: draft
roadmap_ref: ../roadmap.md
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

This plan lands **before** [`postgres-only`](postgres-only.md) and is
written so that plan only has to delete the SQLite half.

## Scope

### 1. Parallel runs

- Add `pytest-xdist` to the dev group. `uv run pytest -n auto` must pass
  for `tests/unit` and `tests/integration` on both backends.
- SQLite in-memory engines are already per-test. For Postgres, each xdist
  worker gets its own database (`<db>_<worker id>`, created on first use
  from the configured `KALETA_DB_URL`, dropped at session end); the
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
- `scripts/verify.sh` runs everything, in parallel (`-n auto`), slow tier
  included — the laptop is where the full suite lives.
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

## Implementation (filled by plan-archiver)
