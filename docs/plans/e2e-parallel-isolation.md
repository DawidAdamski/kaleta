---
plan_id: e2e-parallel-isolation
title: Make the e2e suite safe to run in parallel (per-process ports + storage)
area: tests (e2e harness)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Make the e2e suite safe to run in parallel

## Intent

Enabler for parallel plan work (goal-mode worktrees, one PR per lane). Today
two `./scripts/verify.sh --e2e` runs on the same machine **corrupt each other**,
so lanes that touch `src/kaleta/views/` (which forces `--e2e`, rule 8) cannot
run concurrently. Two root causes, both recorded in `docs/plans/chores.md`:

- **Fixed ports.** `tests/e2e/conftest.py` pins the app to `E2E_PORT = 8081`
  and `tests/e2e/test_auth.py` pins its restartable server to
  `RESTART_PORT = 8084`. `_wait_for_server` accepts whichever server answers,
  so a second run logs in to the *first* run's instance — once that instance's
  `test_mfa` has enrolled 2FA, ~200 tests error with 401s/timeouts. (chores.md:
  "Two e2e runs at once share ports and corrupt each other".)
- **Shared NiceGUI storage.** `conftest.py`'s `e2e_server` does not drop
  `NICEGUI_STORAGE_PATH` from the child env, so two apps share the developer's
  real `~/.kaleta/nicegui` session dir. (chores.md: "e2e servers … inherit
  `NICEGUI_STORAGE_PATH`"; `test_auth.py`'s restart server already pops it.)

- **Shared database server.** Every e2e app runs against the one test
  PostgreSQL (`127.0.0.1:55432`). Two runs collide on it two ways: logically,
  `fresh_database_url` builds a *fixed* name (`kaleta_e2e`, …) so both
  `DROP … WITH (FORCE)` + `CREATE DATABASE "kaleta_e2e"` — the second `CREATE`
  raises `UniqueViolation` and the `DROP` severs the other run's connections
  (observed: `236 errors` / `8 failed`); and physically, piling several heavy
  suites onto one server exhausts it (observed: `server closed the connection
  unexpectedly`, a mid-run crash). The database isolation is therefore handled
  **at the orchestration layer, not in code** — see below.

Fix the per-process resources (ports, storage) in the harness, and give each
parallel lane its **own test-database container** so the lanes never share a
PostgreSQL server at all. Together these make concurrent `--e2e` runs
independent.

Every e2e server port is a hardcoded literal (8081–8089) across nine files, and
`seed_helpers.API_BASE` hardcodes the main server's `8081`. A partial fix still
collides on whatever port is left static, so the whole set moves to per-process
free ports.

- **`tests/e2e/_ports.py`** (new) — the single source of ports, importable
  without a cycle (conftest imports `seed_helpers`, so the picker cannot live in
  conftest):
  - `pick_free_port()` — bind `127.0.0.1:0`, read the OS-assigned port, close,
    return it.
  - `E2E_PORT = pick_free_port()` — the main shared server's port, one per
    pytest process.
- **`tests/e2e/conftest.py`** — import `E2E_PORT` (+ `pick_free_port`) from
  `_ports`; drop the local `E2E_PORT = 8081`. In `e2e_server`, drop
  `NICEGUI_STORAGE_PATH` from the child env, as `test_auth.py`'s restart server
  already does, so session files land under the temp `HOME` (not the dev's real
  `~/.kaleta/nicegui`).
- **`tests/e2e/seed_helpers.py`** — derive `API_BASE` from `_ports.E2E_PORT`
  instead of the `8081` literal.
- **Database isolation — orchestration, no code.** `scripts/test_db.sh` is
  already parameterised by `KALETA_TEST_DB_CONTAINER` (container name) and
  `KALETA_TEST_DB_PORT` (host port). A parallel lane therefore brings up its
  **own** throwaway PostgreSQL and points at it, so lanes never share a server
  (no name collision, no connection-exhaustion crash):

  ```bash
  port=$(python -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
  export KALETA_TEST_DB_CONTAINER=kaleta-pg-$LANE KALETA_TEST_DB_PORT=$port
  export KALETA_DB_URL="$(./scripts/test_db.sh up)"   # own server, own kaleta DB
  ./scripts/verify.sh --e2e
  ./scripts/test_db.sh down                            # tmpfs, nothing kept
  ```

  No change to `suite_database.py`: within a lane the per-app names
  (`kaleta_e2e`, `kaleta_e2e_restart`, …) are already distinct, and they live
  on that lane's private server.
- **The per-file dedicated servers** — replace each hardcoded port with a
  module-level `pick_free_port()` call, and drop `NICEGUI_STORAGE_PATH` from the
  spawned child env where it is not already dropped:
  - `test_auth.py` — `SECURE_COOKIE_PORT`, `RESTART_PORT` (restart reuses its
    one port across restarts, so pick it once at module import).
  - `test_demo_banner.py` — `DEMO_PORT`.
  - `test_encryption_unlock.py` — `ENC_PORT`.
  - `test_tenant_signup.py` — `HOSTED_PORT`, `GOTRUE_PORT`.
  - `test_self_hosted_first_run.py` — `SELF_HOSTED_PORT`.
  - `test_instance_admin.py` — `ADMIN_PORT`.
  - `test_household.py` — `HOUSEHOLD_PORT`.

## Not in scope

- The external-instance path (`KALETA_E2E_BASE_URL`) — unchanged; the port
  logic only applies when the suite spawns its own app.
- `_wait_for_server`'s "first to answer" acceptance — a unique per-process port
  already removes the cross-talk; no change needed there.
- The other flaky-e2e chores (subscription-day, `test_mfa` sign-in, split
  dialog, etc.) — separate items.
- Any `src/` change. This is test-harness only; no user-facing behaviour, so no
  new `KAL-*` scenario.

## Acceptance criteria

- `test -f tests/e2e/_ports.py`
- `grep -q 'def pick_free_port' tests/e2e/_ports.py`
- `test -z "$(grep -rn '= 808[0-9]' tests/e2e/)"` (no hardcoded e2e server port
  literals remain)
- `grep -q 'pick_free_port' tests/e2e/seed_helpers.py`
- `grep -q 'NICEGUI_STORAGE_PATH' tests/e2e/conftest.py`
- `./scripts/verify.sh --e2e` passes on dynamically-chosen ports.
- **Parallel proof:** two `./scripts/verify.sh --e2e` at once, each with its own
  `KALETA_TEST_DB_CONTAINER`/`KALETA_TEST_DB_PORT` (own PostgreSQL), both pass
  (recorded in Implementation notes).

## Touchpoints

`tests/e2e/_ports.py` (new), `tests/e2e/conftest.py`,
`tests/e2e/seed_helpers.py`, `tests/e2e/test_auth.py`,
`tests/e2e/test_demo_banner.py`, `tests/e2e/test_encryption_unlock.py`,
`tests/e2e/test_tenant_signup.py`, `tests/e2e/test_self_hosted_first_run.py`,
`tests/e2e/test_instance_admin.py`, `tests/e2e/test_household.py`.

## Open questions

- **Free-port race.** A port is chosen, the socket closed, then the app binds
  it a moment later — another process could grab it in between. With OS
  ephemeral ports and only a handful of concurrent runs the odds are tiny, and
  `_wait_for_server` already fails loudly if the app never answers. Accepted
  over manual offset bookkeeping.

## Implementation notes

- **Found the blockers by actually running it in parallel.** The ports were the
  known one (chores). Once ports were per-process, a first parallel proof still
  corrupted both runs on the **shared database**: a fixed name
  (`fresh_database_url` → `kaleta_e2e`) collided (`236 errors` for the run that
  lost the `CREATE DATABASE` race; `8 failed` for the one whose connections the
  other's `DROP … WITH FORCE` severed), and separately the single server,
  overloaded by several suites at once, crashed mid-run (`server closed the
  connection unexpectedly`). Shipping only the port fix would have left the
  suite unsafe in parallel — the "prove it" step paid for itself.
- **Database isolation is per-lane containers, not a code change.** An early
  attempt tokened the database *name* (`KALETA_E2E_RUN_ID`) on the shared
  server; it was dropped in favour of giving each lane its own PostgreSQL via
  `scripts/test_db.sh` (already parameterised by `KALETA_TEST_DB_CONTAINER` /
  `KALETA_TEST_DB_PORT`). Separate servers fix *both* failure modes — the name
  collision **and** the connection-exhaustion crash — and need no change to
  `suite_database.py`. So the shipped code is only the per-process ports and
  the storage isolation; the database is handled by the orchestrator.
- **Isolation proof (ports + storage).** Two `uv run pytest tests/e2e -q` at
  once, each on its own dynamically-chosen port (e.g. `127.0.0.1:55817`), ran
  the full suite with **zero** cross-talk once given separate databases —
  `264 passed, 1 failed` each, where the one failure is the pre-existing flaky
  `test_mfa::test_two_factor_authentication` (`/login/mfa` → `/login` bounce,
  chores.md), not a collision. Before the fixes the same two-at-once gave
  `236 errors` / `8 failed`.
- **Operational note for the parallel wave.** Under the extra CPU load of two
  e2e suites at once, that flaky `test_mfa` sign-in failed in *both* lanes (it
  passes on a lone run — a single `verify.sh --e2e` here was 265/265). Each
  parallel goal-mode lane's DoD gate runs `verify.sh --e2e`, so it will hit this
  flake more often and retry. Stabilising or quarantining `test_mfa` (chores.md
  "test_mfa … flaky sign-in") is worth doing before, or alongside, the first
  parallel wave — it is the one test between "lanes run green unattended" and
  "lanes need babysitting".
