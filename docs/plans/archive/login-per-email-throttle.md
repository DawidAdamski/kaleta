---
plan_id: login-per-email-throttle
title: Throttle password sign-in per e-mail, not only per client address
area: auth
effort: small
status: archived
archived_at: 2026-10-24
roadmap_ref: ../../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Throttle password sign-in per e-mail, not only per client address

Origin: chore `docs/plans/chores.md:502`, seen in the review of
`postgres-only` part A.

## Intent
The password form's rate limiter is keyed only by client address
(`login_rate_limiter`, keyed by `_client_key(request)`). So an attacker
guessing passwords for one e-mail from many client addresses is never
locked out — each address stays below the five-failure threshold while
the e-mail takes unbounded guesses. Add a second limiter keyed by the
normalised e-mail so that guessing one e-mail is bounded regardless of
where the attempts come from.

## Scope
Covers:
- A second module-level limiter `login_email_rate_limiter` in
  `src/kaleta/auth/login_rate_limit.py`, reusing the existing
  `LoginRateLimiter` class and config (same lock-out window and
  sentence), with its own store namespace `login_email` so its counters
  never collide with the IP limiter's (`default_store("login_email")`),
  mirroring how `login_rate_limiter` / `mfa_rate_limiter` are declared.
- Wiring both limiters in `src/kaleta/views/login.py::_submit`:
  - IP `is_locked` pre-check at submit start (unchanged).
  - E-mail key = `name.lower()` (the field value is already stripped).
    When `name` is non-empty, an e-mail `is_locked` pre-check too.
  - On `UnauthorizedError`: record a failure on BOTH limiters (e-mail
    only when `name` non-empty). If EITHER reports locked, show
    `auth.login_rate_limited` with the longer remaining lock seconds;
    otherwise `auth.login_failed_email`.
  - On success: clear BOTH limiters (e-mail only when `name` non-empty).
  - Every new limiter call wrapped in the SAME
    `except RATE_LIMITER_BACKEND_ERRORS` fail-closed handling as the
    existing ones (`_rate_limiter_unavailable()` for pre-checks; the
    warning-log-and-continue for `clear`).
  - `EmailNotVerifiedError` (right password) is NOT counted — unchanged.
- Reuse the existing `auth.login_rate_limited` i18n key — same lock-out
  sentence, no new key.
- New scenario KAL-AUTH-042 (`@automated`) in `docs/bdd.md`, covered by
  `tests/integration/test_login_email_throttle.py`.

Does NOT cover:
- Refactoring `_client_key`, the `LoginRateLimiter` class, or the MFA /
  resend limiters.
- Any new user-facing string or i18n key.
- Changing the IP limiter's behaviour.

## Fail-closed behaviour
The e-mail limiter must behave exactly like the IP limiter when its
backend (Redis) is unreachable: a pre-check that cannot reach the counter
fails closed (no sign-in, `common.rate_limit_unavailable` toast via
`_rate_limiter_unavailable()`), and a `clear` after a successful sign-in
that cannot reach the counter logs a warning and continues (the password
was already right; clearing is cleanup, not a gate). Both the IP and the
e-mail call sit inside the same `try/except RATE_LIMITER_BACKEND_ERRORS`
block, so a backend outage can never make the e-mail counter diverge from
the IP counter. `RATE_LIMITER_BACKEND_ERRORS` is empty on a local install
(no `redis`), so this adds no new failure mode there.

## Acceptance criteria
- `uv run pytest tests/integration/test_login_email_throttle.py tests/unit/auth/test_login_rate_limit.py tests/integration/test_auth_hardening.py tests/integration/test_login_rate_limit_replicas.py tests/integration/test_login_rate_limit_backend_down.py -n 2 -m "not slow" -q`
- `uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `grep -q "KAL-AUTH-042" docs/bdd.md`

## Touchpoints
- `src/kaleta/auth/login_rate_limit.py` — new `login_email_rate_limiter`.
- `src/kaleta/views/login.py` — `_submit` wiring.
- `docs/bdd.md` — KAL-AUTH-042.
- `tests/integration/test_login_email_throttle.py` — covering test.
- `docs/plans/chores.md` — tick line 502.

## Open questions
None — design handed down in the chore and the task brief.

## Implementation notes
- The e-mail key is `name.lower()` rather than `name.strip().lower()`:
  `name` is `(username.value or "").strip()`, already stripped, so the
  extra `.strip()` would be a no-op.
- The e-mail pre-check and the per-limiter record/clear are guarded by
  `if name:` — an empty e-mail field has nothing to key on, so the
  e-mail limiter is never touched with an empty key.
- On a double lock the sentence shows `max(secs_ip, secs_email)` so it
  never under-reports the wait.
- The integration test keys two limiters off distinct namespaces
  (`-login`, `-login_email`) and drives five failures for one e-mail from
  five distinct client addresses: the IP limiter locks nothing (no
  address reaches five), the e-mail limiter locks the e-mail for the
  15-minute window. A second test pins that the e-mail key is matched
  case-insensitively (the view lower-cases before keying).

### Landed

- Commit: `00c814b` (PR #368), author Dawid (Ani), merged 2026-10-24.
- Files touched:
  - docs/bdd.md
  - src/kaleta/auth/login_rate_limit.py
  - src/kaleta/views/login.py
  - tests/integration/test_login_email_throttle.py

## Implementation (filled by plan-archiver)
