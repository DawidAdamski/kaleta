---
plan_id: auth-session-rotate-on-login
title: Auth — new session id on login and logout
area: auth
effort: medium
status: draft
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
  ever trips it.
- The `/login/mfa` page today reads `mfa_pending_*` from the bucket.
  Rotation happens *after* the code is accepted, so the pending keys
  are in the old bucket and are dropped by the snapshot filter —
  confirm nothing on the MFA page needs them post-login.

## Implementation notes

_Filled in as work progresses._

## Implementation (filled by plan-archiver)
