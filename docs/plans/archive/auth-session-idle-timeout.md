---
plan_id: auth-session-idle-timeout
title: Auth — idle timeout next to the absolute TTL
area: auth
effort: small
status: archived
archived_at: 2026-09-25
roadmap_ref: ../../roadmap.md#auth
---

# Auth — idle timeout next to the absolute TTL

## Intent

A session ends `KALETA_SESSION_TTL_HOURS` (72) after login and not a
minute sooner, whatever happens in between. A laptop left open on the
transactions page stays signed in for three days. Finance apps
usually pair a hard limit with an idle one: the hard limit bounds how
long a stolen cookie is good for, the idle one bounds how long an
unattended screen is. Kaleta has the first.

Add `KALETA_SESSION_IDLE_HOURS` (default 12, `0` disables) and a
`last_seen_at` stamp that the guards refresh — sparingly, because
every write to `app.storage.user` is a file write.

## Scope

- **Setting**: `session_idle_hours: int = 12`, validator `>= 0`, same
  shape as `session_ttl_hours`. The idle window cannot exceed the
  absolute TTL; the validator caps it and logs, rather than failing
  startup over a config that merely says the same thing twice.
- **Stamp**: `SESSION_LAST_SEEN_AT`, written by `login_session()` and
  refreshed by `touch_session()`. Refresh only when the existing stamp
  is older than `IDLE_TOUCH_INTERVAL_SECONDS = 300`; a busy session
  therefore costs one write per five minutes, not one per request.
- **Guard**: `session_expired()` returns `True` when
  `now - last_seen_at > idle_hours`. A session without the stamp
  (logged in before this shipped) is treated as fresh once — the
  stamp is written on first sight — rather than logged out, unlike the
  legacy-TTL rule; the difference is deliberate and documented in the
  docstring: the TTL rule protects against a missing *login* time, the
  idle rule against a missing *activity* time, and only the first is a
  security fact.
- **Where**: `AuthMiddleware.dispatch` touches after the
  authenticated check passes; `api/deps.get_current_user_id` touches
  on the cookie path. The websocket handshake under `/_nicegui/` is
  public and does not touch — a tab that only keeps a socket open is
  idle.
- **Login page reason**: `/login?reason=idle` with its own line.
- **BDD**: `KAL-AUTH-031` — a session idle longer than the window is
  sent to `/login?reason=idle`; `KAL-AUTH-032` — activity inside the
  window keeps it alive past what the idle window alone would allow,
  up to the absolute TTL.

Out of scope:
- A client-side warning ("you will be signed out in 2 minutes") —
  UI work for a later plan; the server rule comes first.
- Different idle windows per role or per device.

## Acceptance criteria

- `uv run pytest tests/unit/auth/test_session_ttl.py -q`
- `uv run pytest tests/unit/config/ -q`
- `uv run pytest tests/e2e/test_auth.py -q`
- `grep -c "KAL-AUTH-03[12]" docs/bdd.md | grep -qE '^[2-9]'`
- `uv run python scripts/spec_coverage.py`
- `grep -q "KALETA_SESSION_IDLE_HOURS" docs/getting-started.md`
- `uv run mypy src/kaleta/auth src/kaleta/config src/kaleta/api/deps.py`

## Touchpoints

- `src/kaleta/config/settings.py` — setting + validator.
- `src/kaleta/auth/session.py` — stamp, `touch_session()`, guard.
- `src/kaleta/auth/middleware.py`, `src/kaleta/api/deps.py` — touch.
- `src/kaleta/views/login.py` — reason line; i18n `auth.reason_idle`.
- `docs/getting-started.md` — env var table.
- `docs/bdd.md`, `tests/unit/auth/test_session_ttl.py` (extend),
  `tests/e2e/test_auth.py`.

## Open questions

- Default 12 h or 8 h? 12 keeps a normal evening-to-morning gap on a
  home machine signed in; 8 would not. Ship 12, it is one env var to
  change.

## Implementation notes

- **Open question — default:** took the plan default, `12` hours.
- **Cap:** a `model_validator(mode="after")` caps `session_idle_hours` to
  `session_ttl_hours` with a warning. With the TTL off (`0`) there is
  nothing to cap against and the idle value is kept as given.
- **Reason for the redirect:** `session_expired()` still returns a bool for
  its callers; a new `session_expiry_reason()` returns `"ttl"`, `"idle"` or
  `None` so the middleware can add `&reason=idle`. TTL is checked first, so
  a session past both limits is a TTL expiry (plain redirect, as before).
- **Missing activity stamp:** written on first sight inside the guard
  (`_idle_expired`), as the plan asks; an unparseable stamp is treated the
  same way. The asymmetry with the TTL rule is in the docstring.
- **Order in the middleware:** expiry check first, then `touch_session()`;
  touching first would rescue the session the idle rule is about to end.
  The API cookie path touches only when it accepts the request (safe
  methods); a cookie-only POST that gets 401 is not activity.
- **Touch granularity:** the stamp is refreshed at most every 300 s, so a
  session may end up to five minutes before its idle window strictly would.
- **Tests:** `KAL-AUTH-031` guard half is unit-tested against the real
  `AuthMiddleware` class mounted on a bare Starlette app (redirect to
  `/login?redirect_to=…&reason=idle`) and in `tests/integration/test_auth_hardening.py`;
  the login-page line is covered by an e2e test that opens `?reason=idle`
  directly — twelve idle hours do not fit an e2e run. `KAL-AUTH-032` is
  covered in unit and integration tests. `spec_coverage.py` counts only
  `tests/e2e` and `tests/integration`, hence the integration tests.
- The existing `test_session_expired_when_ttl_disabled` now takes the
  `fake_storage` fixture: with the idle rule on by default the guard reads
  storage even when the TTL is off. Its assertion is unchanged.
- Env var also listed in `docs/tech-stack.md` and the `AGENTS.md` env block.

## Implementation (filled by plan-archiver)

## Implementation

Landed on 2026-09-25 (PR #143).

| SHA | Author | Date | Message |
|---|---|---|---|
| `bb2a886` | Dawid Adamski | 2026-09-25 | Merge pull request #143 from DawidAdamski/plan/auth-session-idle-timeout |

**Files changed:**
- AGENTS.md
- docs/bdd.md
- docs/getting-started.md
- docs/plans/auth-session-idle-timeout.md
- docs/tech-stack.md
- src/kaleta/api/deps.py
- src/kaleta/auth/middleware.py
- src/kaleta/auth/session.py
- src/kaleta/config/settings.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/views/login.py
- tests/e2e/test_auth.py
- tests/integration/test_auth_hardening.py
- tests/unit/auth/test_session_ttl.py
- tests/unit/config/test_settings_session_idle.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
