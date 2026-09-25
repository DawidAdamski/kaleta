---
plan_id: auth-session-rotate-on-login
title: Auth — new session id on login and logout
area: auth
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#auth
---

# Auth — new session id on login and logout

## Intent

NiceGUI hands a browser a random storage id on its first request and
never changes it. `login_session()` writes `authenticated`, `user_id`
and the rest into that same bucket; `logout_session()` pops them and
the bucket, its file and the cookie live on. So the id that
identifies an authenticated session is the id the browser had *before*
anyone typed a password. That is the textbook shape of session
fixation: whoever can plant a cookie in a victim's browser (an XSS on
the app, or any script on a sibling subdomain of the hosted domain)
knows the id the victim will be logged in under.

Issue a fresh id when a login completes and when a session ends. The
per-browser preferences that also live in `app.storage.user`
(`dark_mode`, `dashboard_layout`, `language`, `currency`, …) move with
the user; the old bucket is emptied so its file does not keep the
authenticated stamps around until the 30-day sweep.

## Scope

- **The constraint that shapes the design**: `login_session()` runs in
  a button handler, over the websocket. There is no HTTP response in
  flight, so a new id cannot be handed to the browser from there —
  the cookie is written by `SessionMiddleware` on an HTTP response.
  Rotation therefore needs one HTTP round-trip: the login handler
  stores a single-use nonce in the *old* bucket and navigates to a
  plain route; that route (an HTTP request, cookie included) verifies
  the nonce, performs the rotation and redirects to the target page.
- **Nonce**: `SESSION_ROTATE_NONCE` = `secrets.token_urlsafe(32)` plus
  `SESSION_ROTATE_AT`; valid for 60 seconds; consumed on first use;
  the route without a valid nonce redirects to `/login` and does
  nothing else. The nonce carries no user data — the user id is
  already in the bucket, the nonce only proves the navigation came
  from the handler that just authenticated.
- **Rotation** (`auth/session.py: rotate_session_id()`), called from
  the route with a request context:
  1. snapshot `dict(app.storage.user)` minus the nonce keys;
  2. `app.storage.user.clear()` on the old bucket (its file is
     rewritten empty; the sweep removes it later);
  3. `request.session["id"] = str(uuid4())` — NiceGUI resolves
     `app.storage.user` from `request.session["id"]` on every access,
     so the next access is a new bucket;
  4. write the snapshot into the new bucket.
  Documented as relying on `nicegui.storage.RequestTrackingMiddleware`
  behaviour, with a unit test that pins it so a NiceGUI upgrade that
  changes it fails loudly.
- **Login paths**: `views/login.py` (password only),
  `views/login_mfa.py` (after the code), `views/create_account.py` and
  `views/secure_app.py` (first-run flows) all go through the same
  `finish_login(user_id, username, target)` helper that stamps the
  nonce and navigates to `/auth/session/rotate?redirect_to=…`.
- **Logout** (`views/layout.py`): same route with `?logout=1` — pops
  the auth keys, keeps the preferences, rotates, redirects to
  `/login`. A logged-out browser then holds an id that was never
  authenticated.
- **Route**: registered in `auth/__init__.py` next to the middleware
  as a FastAPI route (not a NiceGUI page — it renders nothing). It is
  in `_PUBLIC_UI_PATHS`, since a rotating session is by definition
  not yet authenticated under its new id.
- **BDD**: `KAL-AUTH-026` — the storage cookie value after login
  differs from the one before, and the pre-login id no longer opens a
  data page; `KAL-AUTH-027` — after logout the cookie differs again
  and the theme preference survived both.

Out of scope:
- Cookie flags — [auth-session-cookie-flags](archive/auth-session-cookie-flags.md).
- Moving preferences from per-browser storage to per-user rows in the
  database. That is the right long-term home for `dashboard_layout`
  and friends once there is more than one user per browser, but it is
  a data-model change, not a session one.
- The API bearer path; it has no session to rotate.

## Acceptance criteria

- `uv run pytest tests/unit/auth/test_session_rotation.py -q`
- `uv run pytest tests/e2e/test_auth.py -q`
- `uv run pytest tests/e2e/test_mfa.py -q`
- `grep -c "KAL-AUTH-02[67]" docs/bdd.md | grep -qE '^[2-9]'`
- `uv run python scripts/spec_coverage.py`
- `uv run lint-imports`
- `uv run mypy src/kaleta/auth src/kaleta/views/login.py src/kaleta/views/login_mfa.py src/kaleta/views/layout.py`

## Touchpoints

- `src/kaleta/auth/session.py` — nonce keys, `stamp_rotation_nonce()`,
  `rotate_session_id()`, `finish_login()`.
- `src/kaleta/auth/__init__.py` or a new `auth/routes.py` — the
  rotate route.
- `src/kaleta/auth/middleware.py` — public path entry.
- `src/kaleta/views/login.py`, `login_mfa.py`, `create_account.py`,
  `secure_app.py`, `layout.py` — call the helper instead of
  `login_session()` / `logout_session()` directly.
- `docs/bdd.md` — `KAL-AUTH-026`, `KAL-AUTH-027`.
- `tests/unit/auth/test_session_rotation.py` — new: nonce lifetime
  and single use, snapshot excludes nonce keys, preferences copied,
  old bucket empty, NiceGUI id-resolution pin.
- `tests/e2e/test_auth.py`, `tests/e2e/test_mfa.py` — cookie value
  comparisons around login, MFA and logout.

## Open questions

- Is a 60-second nonce window enough on a slow phone? The navigation
  is immediate; 60 s is generous. Revisit only if the e2e suite on CI
  ever trips it. **Resolved:** kept 60 s — see Implementation notes.
- The `/login/mfa` page today reads `mfa_pending_*` from the bucket.
  Rotation happens *after* the code is accepted, so the pending keys
  are in the old bucket and are dropped by the snapshot filter —
  confirm nothing on the MFA page needs them post-login. **Resolved:**
  nothing does — see Implementation notes (snapshot filter).

## Implementation notes

- **Login is completed under the new id, not the old one.** The plan's
  sketch stamps the auth keys into the old bucket and lets the snapshot
  carry them across. That leaves the fixated id authenticated for one
  round-trip (and forever, if the navigation never happens). Instead
  `finish_login()` parks `rotate_user_id` / `rotate_username` /
  `rotate_mfa_verified` beside the nonce; the route calls
  `login_session()` (and `mark_mfa_verified()` after a code) only after
  `rotate_session_id()`. The nonce still carries no user data. So the
  pre-login id is never authenticated at all, which is stronger than
  KAL-AUTH-026 asks.
- **The nonce travels in the URL** (`?nonce=…`), and the route compares it
  against the bucket with `secrets.compare_digest`. Without that, anyone
  holding the planted cookie could fire the route themselves. A match is
  spent even when it turns out stale or for the wrong purpose. A mismatch
  leaves the stored nonce alone, so a guess can't cancel a real login.
- **Purpose-bound nonces.** `rotate_purpose` is `login` or `logout`, and
  `?logout=1` must agree with it. A logout nonce can't finish a login, and
  the route can't be used as a no-nonce CSRF logout.
- **Logout ends the session in the handler.** `finish_logout()` calls
  `logout_session()` over the websocket first, then stamps the nonce. The
  session is over even if the navigation to the route never happens.
  The route only moves the id.
- **Snapshot filter** drops every auth key (`_AUTH_KEYS`: authenticated,
  user id/name, login/last-seen stamps, `mfa_verified_at`, all
  `mfa_pending_*`) plus the rotation keys. Everything else is a
  preference and moves. Open question 2 is resolved: `/login/mfa` reads the
  `mfa_pending_*` keys only *before* the code is accepted.
  `finish_login` clears them, and after rotation `is_authenticated()` sends
  `/login/mfa` straight to the target, so nothing needs them post-login.
- **Open question 1 (60 s window)**: kept the default, 60 s
  (`ROTATE_NONCE_TTL_SECONDS`).
- **NiceGUI internals.** `rotate_session_id()` must call
  `app.storage._create_user_storage(new_id)` before touching
  `app.storage.user`. `Storage.user` asserts the bucket exists, and only
  `RequestTrackingMiddleware` creates buckets, at the start of a request.
  `tests/unit/auth/test_session_rotation.py` runs the real route behind
  the real `RequestTrackingMiddleware` + `SessionMiddleware` on a
  file-backed `Storage`, so a NiceGUI change to either behaviour fails
  there (checked against NiceGUI 3.17.1). The new bucket can't be pruned
  before the redirect lands: `prune_user_storage` only unloads buckets
  older than 10 s, and it reloads them from disk on the next request anyway.
- **Cookie comparison compares the id, not the raw value.** Starlette
  re-signs `kaleta_session` with a fresh timestamp on every response, so
  the raw value changes on each request whether or not the session moved.
  The tests decode the id from the payload (`tests/e2e/conftest.py:
  storage_id`). The scenarios say "storage id in my cookie" for that reason.
- **Preference survival (KAL-AUTH-027)** is checked by signing in again
  and finding `body.body--dark`. The auth pages don't render the theme,
  so it can't be seen on `/login` itself.
- **`safe_redirect` moved to `kaleta/auth/redirects.py`** (from
  `views/auth_common.py`). The route is in the auth layer and must validate
  `redirect_to`, and the layers contract forbids auth → views. Callers
  (`login.py`, `login_mfa.py`, its unit test) import it from the new place.
  The behaviour is unchanged.
- **Not changed, still in scope's spirit:** a session ended by the TTL or
  idle guard in `AuthMiddleware` is logged out but keeps its id until the
  next login rotates it. That id is no longer authenticated, and the next
  login moves the browser anyway. Rotating there would need the middleware
  to rewrite the cookie on a redirect response, and the plan's scope covers
  only the logout button. The same residual id is left if a logout's
  navigation reaches the route after the 60 s nonce has lapsed. The
  session is already ended by then (`finish_logout()` cleared it over the
  websocket), and the next login rotates the id.
- **DoD gate attempt 2** failed `test_mfa` and `test_quick_entry` while my
  own `verify.sh --e2e` was still running on the same shared e2e port. Both
  passed on their own (test_mfa twice), and the standalone
  `verify.sh --e2e` passed with 191 tests.

## Implementation (filled by plan-archiver)
