---
plan_id: auth-session-idle-timeout
title: Auth — idle timeout next to the absolute TTL
area: auth
effort: small
status: draft
roadmap_ref: ../roadmap.md#auth
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

_Filled in as work progresses._

## Implementation (filled by plan-archiver)
