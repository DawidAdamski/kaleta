---
plan_id: auth-session-hosted-readiness
title: Auth — session state that survives restarts, replicas and a shared disk
area: auth
effort: medium
status: draft
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

_Filled in as work progresses._

## Implementation (filled by plan-archiver)
