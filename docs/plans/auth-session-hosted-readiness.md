---
plan_id: auth-session-hosted-readiness
title: Auth — session state that survives restarts, replicas and a shared disk
area: auth
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#auth
---

# Auth — session state that survives restarts, replicas and a shared disk

## Intent

Three things about session state are true on a laptop and false on a
host. `app.storage.user` is a directory of JSON files under
`~/.kaleta/nicegui`, one per browser, readable by anyone with the
Unix user — fine at home, not fine on a box where the data volume is
shared with other services. `LoginRateLimiter` is a dict in the
process, so two replicas each allow five failures and a restart
allows five more. And `hosted-supabase-rollout` already knows the
storage must move to Redis for a second replica, but nothing in the
repo exercises that mode, so the first time it runs is production.

Close the three before the hosted rollout needs them: lock down the
files, give the limiter a backend, and make the Redis storage mode a
tested configuration rather than a paragraph.

## Scope

- **File permissions**: `NiceguiStorageService.configure_environment`
  creates the directory with mode `0o700` and, because NiceGUI writes
  the files itself, `sweep_stale` and a new `tighten_permissions()`
  chmod existing files to `0o600` at startup. Logged once when any
  file needed fixing. Windows: no-op with a debug line.
- **What may live in the bucket**: a unit test that imports every
  `SESSION_*` constant and asserts none of the values written by
  `auth/session.py` is a secret (no password hash, no TOTP secret, no
  recovery code, no encryption key) — a guard for the ADR-035 rule
  "nothing secret goes into `app.storage.user`", enforced instead of
  remembered.
- **Rate limiter backend**: `LoginRateLimiter` keeps its API
  (`is_locked`, `remaining_lock_seconds`, `record_failure`, `clear`)
  and gains a store: `MemoryStore` (today's dict) and `RedisStore`
  (`INCR` + `EXPIRE` on `kaleta:login:<key>`), chosen by
  `KALETA_REDIS_URL` being set. `redis` becomes an optional extra
  `hosted` next to `postgres`; the import is lazy so the local install
  stays as it is.
- **Storage in Redis, tested**: when `KALETA_REDIS_URL` is set,
  `main.py` exports it as `NICEGUI_REDIS_URL` before importing
  NiceGUI (same place `NICEGUI_STORAGE_PATH` is pinned) and sets
  `NICEGUI_REDIS_KEY_PREFIX=kaleta:`. CI gets a `redis` job (service
  container, like the `postgres` job) that runs the auth unit tests
  and `tests/e2e/test_auth.py` against it. The one-variable design
  means an operator sets `KALETA_REDIS_URL` and both the sessions and
  the limiter move.
- **Docs**: `docs/deployment.md` — the Redis variable, the "single
  replica on a volume" alternative kept as the cheaper option, the
  permission model.
- **BDD**: `KAL-AUTH-033` — with Redis configured, a login survives an
  app restart; `KAL-AUTH-034` — five failed logins on one replica lock
  the account on the other.

Out of scope:
- Moving per-browser preferences (`dark_mode`, `dashboard_layout`, …)
  out of `app.storage.user` into user rows — separate plan, noted in
  `auth-session-rotate-on-login` too.
- Rate limiting anything but login (API token attempts have their own
  plan space).
- Choosing the Redis provider (Upstash vs host Redis) — rollout plan.

## Acceptance criteria

- `uv run pytest tests/unit/auth/ -q`
- `uv run pytest tests/unit/services/test_nicegui_storage_service.py -q`
- `KALETA_REDIS_URL=redis://localhost:6379/0 uv run pytest tests/unit/auth/test_login_rate_limit.py -q`
- `grep -c "KAL-AUTH-03[34]" docs/bdd.md | grep -qE '^[2-9]'`
- `uv run python scripts/spec_coverage.py`
- `grep -q "redis" .github/workflows/ci.yml`
- `grep -q "KALETA_REDIS_URL" docs/deployment.md`
- `uv run lint-imports`
- `[manual]` On a Linux host, `ls -la ~/.kaleta/nicegui` shows `drwx------` and `-rw-------` after one login.

## Touchpoints

- `src/kaleta/services/nicegui_storage_service.py` — modes, `tighten_permissions()`.
- `src/kaleta/auth/login_rate_limit.py` — store protocol, two stores.
- `src/kaleta/config/settings.py` — `redis_url`.
- `src/kaleta/main.py` — env export before the NiceGUI import.
- `pyproject.toml` — `hosted` extra with `redis`.
- `.github/workflows/ci.yml` — `redis` job.
- `docs/deployment.md`, `docs/bdd.md`.
- `tests/unit/auth/test_login_rate_limit.py` (both stores),
  `tests/unit/auth/test_session_contents.py` (new),
  `tests/unit/services/test_nicegui_storage_service.py` (new; the sweep is
  only covered indirectly from `tests/unit/api/test_health.py` today),
  `tests/e2e/test_auth.py`.

## Open questions

- Does the limiter key stay `username` or become `username + client
  IP` once there is a proxy in front? Behind a proxy the IP is
  `X-Forwarded-For`, which is only trustworthy when the proxy is
  known; keep `username` until the rollout plan pins the proxy.
- NiceGUI's Redis persistence keeps a local write-through copy per
  process; confirm with the pinned version that two replicas see each
  other's writes on the *next request* and not only after a pub/sub
  round-trip, and record the answer in implementation notes.

## Implementation notes

- **Limiter key (open question 1).** Default taken: no change to the key.
  Note the password limiter was already keyed by **client IP**, not
  username (`views/login.py`); the MFA limiter by user id. Both stay as they
  are until the rollout plan pins the proxy. Redis keys are
  `kaleta:login:<ip>` and `kaleta:mfa:<user id>` (`<key>:lock` for the lock).
- **NiceGUI Redis sync (open question 2), checked against nicegui 3.17.1.**
  `Storage._users` caches one `RedisPersistentDict` per session id per
  process, loaded from Redis once on that process's first request for the
  id. After that a replica learns about another replica's writes only via
  pub/sub (`<key>changes`), and the writer publishes from a background task
  after the write. So a second replica sees the change *after a pub/sub
  round-trip*, not guaranteed by the next request. Consequence, documented
  in `docs/deployment.md`: keep sticky sessions on the load balancer.
  User keys get no Redis TTL (`ttl=None` for `user-*`); our own
  TTL/idle rules still end the session.
- **Permissions needed a umask, not only a chmod.** NiceGUI saves a session
  by writing `<file>.tmp` and `replace()`-ing it over the old file, so every
  save creates a new inode with the process umask — a `0o600` set at startup
  is gone after the next request, and a fresh login's file was `0o644` (the
  e2e test caught it). `NiceguiStorageService.restrict_new_files()` narrows
  the process umask to `077` (never loosens a stricter one), called at the
  top of `main()` — not at import, so importing `kaleta.main` in tests or
  tools leaves their umask alone. It also makes the DB, backups
  and exports owner-only, which is the same intent — a deliberate widening
  called out in `docs/deployment.md` (a sidecar reading the volume under
  another uid must run as Kaleta's uid). `tighten_permissions()`
  still runs at startup for files left by older versions. Deviation from the
  Scope wording: `sweep_stale()` itself does not chmod — it stays "delete
  old files" — and startup calls `sweep_stale()` then `tighten_permissions()`
  (`main._sweep_nicegui_storage`), which has the same effect.
  `NiceguiStorageService()` now defaults to `NICEGUI_STORAGE_PATH` when set
  (review finding): before, the startup sweep looked at `~/.kaleta/nicegui`
  even when an operator had moved the storage, and so would the tightening. The directory is
  also created `0o700` in `kaleta/__init__.py`, which pins the path first.
- **Clock.** The limiter now uses `time.time()` instead of
  `time.monotonic()`: a lock written by one replica is read by another, and
  monotonic clocks are per process. The `now=` keyword stays and both stores
  honour it (the Redis lock key stores its end time; `EXPIRE` only cleans up).
- **Failure counts expire** `window_seconds` after the first failure, in both
  stores (Redis: `INCR` + `EXPIRE` on the first increment). Before, the
  in-memory count never expired until a lock; a stray failure days apart no
  longer counts towards a lock.
- **Redis down.** The Redis store does not fail open: a login attempt with
  Redis unreachable raises (2 s socket timeouts). In that configuration the
  sessions are in the same Redis, so login cannot work anyway; failing
  closed keeps the limiter from being bypassed by taking Redis down.
  Calls are synchronous (the limiter API is sync); they are single
  round-trips on the login path only.
- **Tests without skips.** Redis-backed tests use the server at
  `KALETA_REDIS_URL` when set and an in-process `fakeredis` server otherwise
  (`fakeredis` + `redis` added to the dev group), so the Redis code path runs
  on every `pytest`. KAL-AUTH-034 is covered by
  `tests/integration/test_login_rate_limit_replicas.py` (spec_coverage only
  reads e2e/integration), KAL-AUTH-033 by
  `tests/e2e/test_auth.py::test_login_survives_an_app_restart`, which runs
  in both modes and, in file mode, also asserts `0700`/`0600` on the session
  directory and files — the automated half of the `[manual]` criterion.
- **e2e storage path.** The restart test's app drops the inherited
  `NICEGUI_STORAGE_PATH` (importing `kaleta` in the pytest process pins it to
  the developer's `~/.kaleta`); the other e2e servers still inherit it — a
  pre-existing quirk, added to `docs/plans/chores.md`.
- **CI `redis` job** installs `--extra hosted` and Playwright chromium, then
  runs the auth unit tests, the replica integration test and
  `tests/e2e/test_auth.py` with `KALETA_REDIS_URL` set. `tests/e2e/test_auth.py`
  passes locally against `redis:7` (13 passed).

## Implementation (filled by plan-archiver)
