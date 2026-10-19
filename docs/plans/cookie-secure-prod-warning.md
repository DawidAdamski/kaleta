---
plan_id: cookie-secure-prod-warning
title: Warn when a production run serves the session cookie without Secure
area: security (auth)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Warn when a production run serves the session cookie without Secure

## Intent
Security assessment finding **F-3** (`docs/security/assessment-2026-10-12.md`):
`session_cookie_secure` defaults to `False` — a deliberate choice so plain-http
dev installs work — and there is a start-up warning when `Secure` is turned *on*
in debug (`warn_secure_cookie_in_debug`), but **no warning when it is left off
in a production-shaped run** (debug false). A multi-family instance that serves
the session cookie over plain http lets anyone on the network path read it and
hijack a session.

This slice adds the missing start-up warning: when `KALETA_DEBUG` is false and
`session_cookie_secure` is false, log that the cookie is served without `Secure`
and that it should be enabled behind TLS.

### Warn, not refuse (binding decision)
The assessment says "warn (or refuse)". We **warn**, not refuse — unlike the
placeholder `secret_key` (which is never valid in production and so is a hard
refuse), a plain-http production run is a *legitimate* deployment: an instance
behind a TLS-terminating reverse proxy that forwards http, or a trusted-LAN
install. The app has no reliable signal at config time that TLS is present, so
refusing would break valid setups. A loud start-up warning is the right,
non-breaking remediation; the operator sets `KALETA_SESSION_COOKIE_SECURE=true`
once TLS is in front.

## Scope
- **`src/kaleta/auth/session.py`**: add `warn_insecure_cookie_in_production(cfg)`
  — a sibling of `warn_secure_cookie_in_debug`, the opposite condition — that
  warns when `not cfg.debug and not cfg.session_cookie_secure`. The two
  conditions are mutually exclusive, so both are safe to call at start-up.
- **`src/kaleta/main.py`**: call it in `run_web()`, right after
  `warn_secure_cookie_in_debug()`.
- **`docs/bdd.md`**: add **KAL-SEC-003 @automated** — a production run without a
  `Secure` cookie logs a warning (and a dev run, or a secure production run,
  does not).
- **`docs/security/assessment-2026-10-12.md`**: flip F-3 to **Fixed** with the
  KAL-SEC-003 reference.
- Tests: `tests/integration/test_cookie_security.py` (new) — warns when
  `debug=False, secure=False`; silent when dev, or when secure is on in
  production. It lives in `tests/integration` (not `unit`) because
  `spec_coverage` scans only integration + e2e for an `@automated` scenario's
  cover, even though the test itself needs no database.

**Not in scope (binding):**
- No change to the `session_cookie_secure` default (it stays `False` for
  http-only installs) or to the cookie kwargs.
- No hard refusal — see the binding decision above.
- F-4 (upload byte cap) is its own slice.

## Acceptance criteria
- `uv run pytest tests/integration/test_cookie_security.py -q`
- `./scripts/verify.sh` (no `src/kaleta/views/` change → short gate)
- Fail-on-old: the new test asserts a warning is logged when `debug=False,
  secure=False`; on the pre-change code there is no such warning (the function
  does not exist / is never called) → the test fails. Verified by a backup swap
  (neutralise the new warn call).

## Touchpoints
- `src/kaleta/auth/session.py`
- `src/kaleta/main.py`
- `tests/integration/test_cookie_security.py` (new)
- `docs/bdd.md`
- `docs/security/assessment-2026-10-12.md`
- `docs/plans/chores.md` (the security chore note)

## Open questions
- None blocking. Warn-not-refuse is recorded above.

## Implementation notes
- **Warn, not refuse.** Recorded in the binding decision above and in the
  assessment F-3 entry: a plain-http production run is legitimate behind a TLS
  proxy / on a trusted LAN, and the app cannot detect TLS at config time, so a
  hard refusal (as for the placeholder `secret_key`) would break valid setups.
- **A sibling, not a rename.** `warn_insecure_cookie_in_production` is added
  next to `warn_secure_cookie_in_debug` rather than folding both into one
  function, so the existing function and its unit tests are untouched. The two
  conditions are mutually exclusive (`secure and debug` vs `not debug and not
  secure`), so `run_web()` calls both back to back with no risk of a double
  warning.
- **The cover lives in `tests/integration`.** The function is pure logging and
  needs no DB, but `spec_coverage` scans only `tests/integration` and
  `tests/e2e` for an `@automated` scenario's covering test, so the KAL-SEC-003
  cover is `tests/integration/test_cookie_security.py`, not a unit test.
- **Production `Settings` needs a real secret.** A `Settings(debug=False, …)`
  with the placeholder key raises (the existing `secret_key` guard), so the
  production-tier test passes `secret_key="s" * 32`.
- **Fail-on-old verified.** Commenting out the `warn_insecure_cookie_in_production()`
  call in `run_web` does not fail the unit test (it calls the function directly),
  but neutralising the function body (making it a no-op, a backup swap) makes
  `test_warns_when_production_serves_cookie_without_secure` fail on the missing
  warning; restoring it restores green. The warning text itself is the new
  behaviour that did not exist before this slice.
