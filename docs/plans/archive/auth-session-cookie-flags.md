---
plan_id: auth-session-cookie-flags
title: Auth — session cookie flags and lifetime
area: auth
effort: small
status: archived
archived_at: 2026-09-24
roadmap_ref: ../../roadmap.md#auth
---

# Auth — session cookie flags and lifetime

## Intent

`ui.run()` passes NiceGUI only `storage_secret`, so the session cookie
that carries the storage id is whatever Starlette's `SessionMiddleware`
does by default: no `Secure` flag, `SameSite=Lax`, a 14-day `max_age`,
the name `session`. On `127.0.0.1` none of that matters. Behind TLS on
a public host it does: a cookie without `Secure` is sent over any
plain-http request to the same host, and a cookie that outlives
`KALETA_SESSION_TTL_HOURS` (72 h) by eleven days keeps pointing at a
storage file the app already treats as logged out.

NiceGUI forwards `session_middleware_kwargs` straight into
`SessionMiddleware`. Set them from configuration, with defaults that
keep local use unchanged and one switch that hosted deployments flip.

## Scope

- **Settings** (`config/settings.py`):
  - `session_cookie_secure: bool = False` (`KALETA_SESSION_COOKIE_SECURE`).
    `True` sets `https_only`; the browser then never sends the cookie
    over http, so login on plain http silently stops working — the
    setting's docstring and `deployment.md` say so.
  - `session_cookie_samesite: Literal["lax", "strict"] = "lax"`
    (`KALETA_SESSION_COOKIE_SAMESITE`). `strict` is offered, not
    defaulted: it drops the cookie on any navigation that starts
    outside the app, which includes the "confirm your e-mail" links of
    the hosted sign-up flow.
  - Cookie `max_age` derived, not configured: `session_ttl_hours *
    3600` when the TTL is on, Starlette's default when it is `0`.
  - Cookie name `kaleta_session`, so two NiceGUI apps on one host
    stop sharing a cookie. Renaming logs every browser out once; the
    release note says so.
- **Wiring** (`main.py`): one helper `session_middleware_kwargs()`
  in `auth/session.py` (pure, no NiceGUI import at call time) that
  both `run_web` and `run_app` pass as
  `ui.run(..., session_middleware_kwargs=...)`. `run_api` has no
  NiceGUI session and is untouched.
- **Startup guard**: `secure=True` with `host=127.0.0.1` and no
  reverse proxy is the usual foot-gun; log a warning at startup when
  `session_cookie_secure` is on and `debug` is on, since that is the
  combination a developer hits when copying the hosted env file.
- **Docs**: `docs/deployment.md` gets the two variables in the env
  block next to `KALETA_SECRET_KEY`; `docs/getting-started.md` lists
  them with the other `KALETA_*` settings.
- **BDD**: `KAL-AUTH-025` — with the secure flag on, the login
  response's `Set-Cookie` carries `Secure`, `HttpOnly`, `SameSite`
  and a `Max-Age` equal to the session TTL.

Out of scope:
- Rotating the cookie value on login — [auth-session-rotate-on-login](auth-session-rotate-on-login.md).
- Any change to what the session stores.
- Detecting TLS automatically from `X-Forwarded-Proto`; an explicit
  setting is less magic and matches how `KALETA_SECRET_KEY` is handled.

## Acceptance criteria

- `uv run pytest tests/unit/auth/test_session_cookie.py -q`
- `uv run pytest tests/unit/config/ -q`
- `grep -c "KAL-AUTH-025" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- `grep -q "KALETA_SESSION_COOKIE_SECURE" docs/deployment.md`
- `grep -q "session_middleware_kwargs" src/kaleta/main.py`
- `uv run mypy src/kaleta/auth src/kaleta/config src/kaleta/main.py`

## Touchpoints

- `src/kaleta/config/settings.py` — two settings, validators.
- `src/kaleta/auth/session.py` — `session_middleware_kwargs()`.
- `src/kaleta/main.py` — pass the kwargs in `run_web` / `run_app`.
- `docs/deployment.md`, `docs/getting-started.md`.
- `docs/bdd.md` — `KAL-AUTH-025`.
- `tests/unit/auth/test_session_cookie.py` — new: kwargs for each
  settings combination, `max_age` follows the TTL, name is
  `kaleta_session`.
- `tests/e2e/test_auth.py` — one scenario reading `Set-Cookie` on the
  login response with the flag on (runs the app with the env set).

## Open questions

- Keep the cookie name `session` to avoid the one-time logout, or
  rename now while the user base is one person? Leaning rename.

## Implementation notes

- **Open question — cookie name:** took the default, renamed to
  `kaleta_session` (`auth.session.SESSION_COOKIE_NAME`). Every browser is
  signed out once; the release note is in `docs/deployment.md`.
- `session_middleware_kwargs(cfg=None)` takes an optional `Settings` so tests
  build one per combination instead of monkeypatching the global. With the
  TTL at `0` the `max_age` key is omitted, so Starlette's own 14-day default
  applies (the plan's wording) rather than a value we would have to keep in
  sync with Starlette.
- `session_cookie_samesite` is lower-cased before the `Literal` check, so
  `KALETA_SESSION_COOKIE_SAMESITE=Strict` works; `none` is rejected (it would
  need `Secure` and has no use in a same-origin app).
- **Startup warning placement:** `warn_secure_cookie_in_debug()` runs right
  after `_warn_repo_root_data_leftovers()`, not just before `ui.run()`. A
  WARNING logged after `_register_views()` reaches the log ring buffer's
  resolver `views.error_handling.current_client_id`, whose `context.client`
  access flips NiceGUI into script mode and `ui.run()` then refuses to start.
  That latent bug is pre-existing and outside this scope; it is recorded in
  `docs/plans/chores.md`.
- **KAL-AUTH-025** is covered twice: a unit test feeds the kwargs to a real
  `SessionMiddleware` and reads `Set-Cookie`; the e2e test starts an isolated
  app on its own port (8083) with `KALETA_SESSION_COOKIE_SECURE=true` and reads
  `Set-Cookie` on `GET /login` with httpx (a browser is not needed to read a
  header, and would drop a `Secure` cookie on plain http anyway). It also
  asserts the debug-mode startup warning in the server log.
  `_ensure_e2e_user_subprocess` moved from `test_demo_banner.py` into
  `tests/e2e/conftest.py` so both second-server fixtures share it.

## Implementation (filled by plan-archiver)

## Implementation

Landed on 2026-09-24 (PR #138).

| SHA | Author | Date | Message |
|---|---|---|---|
| `e33dd17` | Dawid Adamski | 2026-09-25 | Merge pull request #138 from DawidAdamski/plan/auth-session-cookie-flags |

**Files changed:**
- docs/bdd.md
- docs/deployment.md
- docs/getting-started.md
- docs/plans/auth-session-cookie-flags.md
- docs/plans/chores.md
- src/kaleta/auth/session.py
- src/kaleta/config/settings.py
- src/kaleta/main.py
- tests/e2e/conftest.py
- tests/e2e/test_auth.py
- tests/e2e/test_demo_banner.py
- tests/unit/auth/test_session_cookie.py
- tests/unit/config/test_settings_session_cookie.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
