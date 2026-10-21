---
plan_id: rate-limiter-login-toast
title: Surface a toast when the login/MFA rate limiter's backend is unreachable
area: auth / views
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#open-core
---

# Surface a toast when the login/MFA rate limiter's backend is unreachable

## Intent
With `KALETA_REDIS_URL` set and Redis unreachable, the login/MFA rate limiter
fails closed (by design): every limiter method raises
`redis.exceptions.ConnectionError`. The click handlers in `views/login.py`,
`views/login_mfa.py` and `views/settings/security_tab.py` do **not** catch that
exception, so the handler coroutine dies and the user sees nothing at all — the
Log in / Verify / MFA-dialog button simply does nothing. Surface the failure as
a localized "try again shortly" toast and stop the protected action, instead of
silently dying.

## Scope
Covers:
- A narrow, install-safe exception set `RATE_LIMITER_BACKEND_ERRORS` in
  `src/kaleta/auth/login_rate_limit.py` (guarded import of
  `redis.exceptions.RedisError`; empty tuple when the `hosted` extra is absent,
  where the store is `MemoryStore` and never fails). This is the exact set the
  views catch — it matches what the limiter actually raises when Redis is down.
- Wrapping every `login_rate_limiter` / `mfa_rate_limiter` call in the three
  views so a backend failure is caught and surfaced:
  - the `is_locked` gate (+ its `remaining_lock_seconds`) and `record_failure`
    (+ `remaining_lock_seconds`) → warning toast, action does **not** proceed
    (fail closed);
  - `clear()` on the success path → best-effort: a backend error is swallowed
    (logged) so a correct credential is **not** blocked by a cleanup that could
    not reach Redis. Fail-closed is about denying access when the gate cannot be
    checked; `clear` runs after access was already granted, so there is nothing
    to deny.
- One shared i18n key `common.rate_limit_unavailable` in `en.json` + `pl.json`.
- BDD scenario KAL-AUTH-041 + an integration regression test for the mechanism.

Does **not** cover:
- Changing the fail-closed behaviour itself (the limiter still raises).
- Any refactor of the limiter's semantics beyond the exception-set constant.
- NiceGUI session storage behaviour under an unreachable Redis (out of scope;
  the same `KALETA_REDIS_URL` also backs NiceGUI storage — see Implementation
  notes for why this blocks a faithful e2e).

## Acceptance criteria

- `uv run pytest tests/integration/test_login_rate_limit_backend_down.py -q`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python -c "import json; a=json.load(open('src/kaleta/i18n/locales/en.json')); b=json.load(open('src/kaleta/i18n/locales/pl.json')); assert a['common']['rate_limit_unavailable'] and b['common']['rate_limit_unavailable']"`

## Touchpoints
- `src/kaleta/auth/login_rate_limit.py` (add `RATE_LIMITER_BACKEND_ERRORS`)
- `src/kaleta/views/login.py`
- `src/kaleta/views/login_mfa.py`
- `src/kaleta/views/settings/security_tab.py`
- `src/kaleta/i18n/locales/en.json`, `.../pl.json` (`common.rate_limit_unavailable`)
- `tests/integration/test_login_rate_limit_backend_down.py`
- `docs/bdd.md` (KAL-AUTH-041)

## Open questions
None blocking. Defaults taken (recorded below).

## Implementation notes
- **Exact exception.** Probed `RedisStore` against an unreachable address: every
  method (`is_locked`, `remaining_lock_seconds`, `record_failure`, `clear`)
  raises `redis.exceptions.ConnectionError`, a subclass of
  `redis.exceptions.RedisError`. The views therefore catch
  `RATE_LIMITER_BACKEND_ERRORS = (redis.exceptions.RedisError,)` — narrow, not a
  bare `except`. When `redis` is not installed (no `hosted` extra), the store is
  `MemoryStore`, which cannot fail, and the tuple is empty (`except ()` catches
  nothing) — correct.
- **Why not a faithful e2e.** The reported trigger is "`KALETA_REDIS_URL` set and
  Redis unreachable". But that same variable also moves NiceGUI's *session
  storage* to Redis (`main.py` → `NiceguiStorageService.configure_environment`).
  `/login`'s page handler calls `is_authenticated()`, which reads
  `app.storage.user`; with Redis down that read raises and the page 500s **before**
  the submit handler ever runs. So the only faithful trigger also takes down the
  storage the page needs to render — the toast cannot be reproduced in the e2e
  harness. An in-process NiceGUI `User` test would need to execute `main.py`'s
  full lifespan in-process (brand-new harness, reconciled with the suite DB) —
  a disproportionate ripple for a chore, and beyond this plan's scope.
- **What is automated.** `tests/integration/test_login_rate_limit_backend_down.py`
  asserts the load-bearing fact: when the limiter's Redis backend is unreachable,
  its methods raise an exception that `RATE_LIMITER_BACKEND_ERRORS` catches, and
  the tuple is non-empty when `redis` is importable. That is exactly the contract
  the three views rely on; if redis ever changed its exception type, or the tuple
  were empty, this test fails. The visible toast + "not signed in" is tagged
  `@manual` on KAL-AUTH-041 (verified by inspection + by hand against a degraded
  deployment).
- **Default taken:** one shared key `common.rate_limit_unavailable` (not per-page)
  since the message is identical across login, MFA and the security dialogs.
