---
plan_id: auth-session-revocation
title: Auth — revoke sessions from the server
area: auth
effort: medium
status: archived
archived_at: 2026-09-27
roadmap_ref: ../../roadmap.md#auth
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

- **Migration parent.** The plan says "after `m7n8o9p0q1r2_add_user_mfa`";
  the head had since moved to `n8o9p0q1r2s3`, so the new revision
  `o9p0q1r2s3t4` revises that, to keep one head.
- **Cache invalidation crosses a layer boundary, so it lives above it.**
  `kaleta.auth` sits above `kaleta.services` in the import-linter layers, so
  `AuthService.revoke_sessions` cannot call `revocation_cache.forget()`. The
  UI callers do it: `keep_session_after_revocation()` (MFA changes) and the
  Sign out everywhere handler both forget the entry. The CLI and
  `disable_all()` run in another process anyway, which the 60-second bound
  covers.
- **The browser that changes the second factor stays signed in.** Otherwise
  turning MFA on would throw the user out while the recovery codes were on
  screen. The plan does not decide this, so the default follows GitHub and
  Google: every *other* session goes. Mechanism: a separate
  `SESSION_REVALIDATED_AT` stamp that the guard reads as
  `max(login_at, revalidated_at)`. `login_at` does not move, because moving
  it would restart the absolute TTL. Sign out everywhere does not keep the
  current session, as the plan says. Recorded as `KAL-AUTH-035` (033 and 034
  are reserved by `auth-session-hosted-readiness`).
- **The API cookie path refuses a revoked session but does not end it.**
  `authenticated_user_id()` returns `None` (→ 401) and leaves the bucket
  alone. The page guard is the one that ends it, and it is also what adds
  `?reason=signed_out_everywhere`. If a background API call emptied the
  session first, the next page load would reach `/login` with no reason
  given. Each refusal costs one cached lookup.
- **New seam `authenticated_user_id(request)`** (async) wraps the sync
  `user_id_from_request` plus the revocation check. Two existing tests
  stubbed `deps.user_id_from_request`, and now stub this seam instead. Their
  assertions are unchanged.
- **Open question 1 (every request vs page loads):** default taken. The check
  runs in `AuthMiddleware` after the expiry check and before `touch_session`,
  and `/_nicegui/*` is already public, so only page navigations pay for it.
- **Open question 2 (Redis cache):** not done, per the default; the one-minute
  bound is documented in `SECURITY.md` and `docs/getting-started.md`.
- **A session with no `login_at`** is treated as revoked once a watermark
  exists, the same stance `_ttl_expired` takes on a missing stamp.
- **Sign out everywhere**: a confirm dialog comes first, then `_step_up` (a
  no-op with MFA off). The service method itself is unguarded, because
  revoking only takes access away. The step-up is there so that a stolen
  cookie cannot throw the owner out.
- **e2e isolation.** Any bump also ends the suite's shared
  `auth_storage_state` login (including `seed_helpers.disable_mfa_for_all()`
  in `test_mfa.py`'s teardown). New fixture `renew_shared_login` signs in
  again afterwards and updates that dict in place.
  `no_enrolment_left_behind` depends on it, so the re-login happens after
  the enrolment is gone.
- **Coverage split.** `scripts/spec_coverage.py` counts only e2e and
  integration tests. A shell reset reaches the running server only once its
  60-second cache has lapsed, which is too slow for e2e, so KAL-AUTH-028 and
  KAL-AUTH-035 are covered in
  `tests/integration/test_session_revocation_guards.py` against the real
  middleware and a real database. KAL-AUTH-029 and KAL-AUTH-030 are covered
  in e2e by `test_sign_out_everywhere_ends_every_browser`.

- **CI: `test_aggregates_under_200ms_on_a_thousand_transactions` failed
  (420 ms, then 372 ms) on the SQLite unit job; `main` and this branch's
  Postgres job passed.** Root cause: the aggregation takes ~11 ms. The rest
  was a full (gen-2) garbage collection landing inside the timed window. By
  that test the unit suite's heap holds ~680k objects, and one gen-2 pass
  measured 121 ms locally on Python 3.13 (~3× that on the runner). This
  branch's 23 extra tests leave ~11k more objects alive, which moved the
  point where the collector fires into the window. It is not a regression
  in the service. Fix, in its own commit: `gc.collect()` before
  `perf_counter()`. The 200 ms bound is unchanged. It belongs to another
  area, but it blocks this PR's CI, so it is fixed here rather than left in
  the chore inbox.

## Implementation (filled by plan-archiver)

## Implementation

Landed on 2026-09-27 (PR #153).

| SHA | Author | Date | Message |
|---|---|---|---|
| `527ffd8` | Dawid Adamski | 2026-09-27 | Merge pull request #153 from DawidAdamski/plan/auth-session-revocation |

**Files changed:**
- SECURITY.md
- alembic/versions/o9p0q1r2s3t4_add_user_sessions_valid_from.py
- docs/bdd.md
- docs/getting-started.md
- docs/plans/auth-session-revocation.md
- src/kaleta/api/deps.py
- src/kaleta/auth/middleware.py
- src/kaleta/auth/revocation_cache.py
- src/kaleta/auth/session.py
- src/kaleta/cli/reset_password.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/models/user.py
- src/kaleta/services/auth_service.py
- src/kaleta/services/mfa_service.py
- src/kaleta/views/login.py
- src/kaleta/views/settings/security_tab.py
- tests/e2e/conftest.py
- tests/e2e/test_auth.py
- tests/e2e/test_mfa.py
- tests/integration/test_api_cookie_auth.py
- tests/integration/test_session_revocation_guards.py
- tests/unit/auth/test_session_revocation.py
- tests/unit/auth/test_session_ttl.py
- tests/unit/cli/test_reset_password.py
- tests/unit/services/test_mfa_service.py
- tests/unit/services/test_wizard_action_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
