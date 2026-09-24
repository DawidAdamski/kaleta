---
plan_id: auth-session-revocation
title: Auth — revoke sessions from the server
area: auth
effort: medium
status: draft
roadmap_ref: ../roadmap.md#auth
---

# Auth — revoke sessions from the server

## Intent

Nothing on the server can end a session it did not start. Sessions are
files keyed by a browser id; there is no index from a user to the
browsers logged in as them. So after `kaleta reset-password` the CLI
prints *"Existing browser sessions may still work until you sign out"*
— which is the honest description of a gap: the one moment a person
resets a password is the moment they most want every other browser
out. Enabling or disabling two-factor, and regenerating recovery
codes, have the same hole.

Give the user row a watermark, `sessions_valid_from`, that every
credential-changing action bumps, and have the guards refuse any
session whose `login_at` is older than it. That needs no index of
sessions, works with file storage today and Redis later, and gives
Settings a "sign out everywhere" button for free.

## Scope

- **Model + migration**: `User.sessions_valid_from: datetime | None`
  (UTC, nullable; `NULL` means "never revoked" so existing rows need no
  backfill). Alembic revision after `m7n8o9p0q1r2_add_user_mfa`.
- **Bumps** (all through one `AuthService.revoke_sessions(user_id)`):
  - `AuthService.reset_password` (the CLI path) — always.
  - `MfaService.confirm_enrolment`, `disable`, `disable_all`,
    `regenerate_recovery_codes`.
  - Settings → Security: a **Sign out everywhere** button, behind the
    MFA step-up when MFA is on (`step_up_required`), which bumps the
    watermark and then ends the current session too.
  The CLI message changes to *"All browser sessions have been signed
  out; API bearer tokens are unchanged."*
- **Guard**: `session_expired()` today compares `login_at` with the
  TTL; it gains a second clause, `login_at < sessions_valid_from`. The
  watermark is read through a small per-process cache
  (`auth/revocation_cache.py`: `user_id → (valid_from, fetched_at)`,
  60-second TTL) so the UI middleware does not hit the database on
  every request; the bump path invalidates the cache entry for that
  user in the same process. A second replica sees the bump within a
  minute, which is the documented bound.
- **Where the guard runs**: `AuthMiddleware.dispatch` (UI pages) and
  `api/deps.get_current_user_id` (cookie path only — bearer tokens
  have their own revocation in `ApiTokenService`). `session_expired()`
  is sync today and reads only the bucket; the watermark lookup is
  async, so the check moves to an `async def session_revoked(user_id,
  login_at)` that both callers await, and `session_expired()` keeps
  its current meaning.
- **Reason on the login page**: a revoked session lands on
  `/login?reason=signed_out_everywhere` with a one-line explanation,
  same pattern as `mfa_expired`.
- **BDD**: `KAL-AUTH-028` — after `reset-password`, a browser that was
  logged in is sent to `/login` with the reason on its next page load;
  `KAL-AUTH-029` — "Sign out everywhere" ends a second browser's
  session and the current one; `KAL-AUTH-030` — an API `GET` with the
  revoked session cookie gets 401.

Out of scope:
- Listing active sessions (device, last seen) with per-session
  revocation — needs the index this plan deliberately avoids; a
  natural follow-up once storage is in Redis.
- Bearer token revocation — exists.
- Hosted `supabase` auth backend: Supabase issues its own refresh
  tokens; the NiceGUI session that fronts them still gets the
  watermark, bumped from the Supabase auth-event hook
  (`hosted-tenancy-foundation` owns that hook).

## Acceptance criteria

- `uv run alembic upgrade head`
- `uv run pytest tests/unit/auth/test_session_revocation.py -q`
- `uv run pytest tests/unit/cli/test_reset_password.py -q`
- `uv run pytest tests/unit/services/test_mfa_service.py -q`
- `uv run pytest tests/e2e/test_auth.py -q`
- `grep -c "KAL-AUTH-0(28|29|30)" -E docs/bdd.md | grep -qE '^[3-9]'`
- `uv run python scripts/spec_coverage.py`
- `uv run lint-imports`
- `test "$(grep -c 'Existing browser sessions may still work' src/kaleta/cli/reset_password.py)" -eq 0`

## Touchpoints

- `src/kaleta/models/user.py`, `alembic/versions/<new>_sessions_valid_from.py`.
- `src/kaleta/services/auth_service.py` — `revoke_sessions`,
  `reset_password` calls it.
- `src/kaleta/services/mfa_service.py` — four call sites.
- `src/kaleta/auth/session.py` — `session_revoked()`.
- `src/kaleta/auth/revocation_cache.py` — new.
- `src/kaleta/auth/middleware.py`, `src/kaleta/api/deps.py` — await
  the check.
- `src/kaleta/views/settings/security_tab.py` — the button;
  `src/kaleta/views/login.py` — the reason text; i18n keys
  `auth.reason_signed_out_everywhere`, `settings.sign_out_everywhere`.
- `src/kaleta/cli/reset_password.py` — message.
- `docs/bdd.md`, `tests/unit/auth/test_session_revocation.py`,
  `tests/e2e/test_auth.py`.

## Open questions

- Should the middleware's async watermark check run on every request
  or only on page navigations (skip `/_nicegui/*` websocket
  handshakes)? Page loads are enough — a revoked session's open
  websocket can keep the current page alive until the next
  navigation, and the 60-second cache bounds that anyway.
- Cache in Redis when `NICEGUI_REDIS_URL` is set, so replicas see a
  bump instantly? Not in this plan; the one-minute bound is stated in
  the docs and is fine for a household app.

## Implementation notes

_Filled in as work progresses._

## Implementation (filled by plan-archiver)
