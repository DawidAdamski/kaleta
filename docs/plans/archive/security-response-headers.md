---
plan_id: security-response-headers
title: Set security response headers on the web app (F-8)
area: security (http hardening)
effort: small
status: archived
archived_at: 2026-10-21
roadmap_ref: ../../roadmap.md
---

# Set security response headers on the web app (F-8)

## Intent

The ZAP baseline (`security-zap-baseline`, finding **F-8**, Medium) found the
app sets none of the standard security response headers, so clickjacking and
MIME-sniffing vectors are not closed at the edge. Add a response-headers
middleware that stamps a sensible, NiceGUI-safe set on every web response.

## Scope

- **`src/kaleta/security_headers.py`** (new) — a pure-ASGI
  `SecurityHeadersMiddleware` (mirroring `RequestContextMiddleware` in
  `logging_config.py`); it is wired by `main._register_security_headers()`
  (mirroring `_register_request_context`). It stamps on the
  `http.response.start` of every HTTP response:
  - `Content-Security-Policy` — a default tuned to what NiceGUI/Vue needs:
    `default-src 'self'`; `script-src 'self' 'unsafe-inline' 'unsafe-eval'`
    (inline SW registration + NiceGUI/Vue bootstrap + eval);
    `style-src 'self' 'unsafe-inline'` (inline `<style>` + Quasar);
    `connect-src 'self' ws: wss:` (the Socket.IO websocket);
    `img-src 'self' data:`; `font-src 'self'`; `manifest-src 'self'`;
    `worker-src 'self'`; `frame-ancestors 'none'`; `base-uri 'self'`;
    `form-action 'self'`; `object-src 'none'`.
  - `X-Frame-Options: DENY` (+ `frame-ancestors 'none'`) — clickjacking (10020).
  - `X-Content-Type-Options: nosniff` (10021).
  - `Referrer-Policy: strict-origin-when-cross-origin`.
  - `Permissions-Policy` — lock down the powerful features we never use.
  - `Strict-Transport-Security` — **only** when `session_cookie_secure` is on
    (i.e. TLS in front), reusing the existing F-3 signal so a legitimate
    plain-http-behind-proxy / localhost install is never sent HSTS.
- **`src/kaleta/config/settings.py`** — one toggle
  `security_headers_enabled: bool = True` (env
  `KALETA_SECURITY_HEADERS_ENABLED`), mirroring `session_cookie_secure`. An
  escape hatch for an unusual deploy; on by default.
- **`src/kaleta/main.py`** — a `_register_security_headers()` called **last** in
  `run_web()` (after `_register_auth()`), so the middleware is outermost and
  stamps headers on every response, including the `RedirectResponse`es
  `AuthMiddleware` returns.
- **`docs/bdd.md`** — `KAL-SEC-006 @automated`.
- **`tests/integration/test_security_headers.py`** (new, `Covers: KAL-SEC-006`)
  — drive the middleware through a small app over httpx: the CSP + the smaller
  headers are present on a normal response and on a redirect; HSTS appears only
  when `session_cookie_secure`; the toggle off removes them all.
- **`docs/security/assessment-2026-10-12.md`** + **`docs/plans/chores.md`** —
  flip F-8 → Fixed and tick the chore, after a real ZAP re-run confirms the
  WARNs drop.

## Not in scope

- **The Spectre site-isolation set (COOP/COEP/CORP, ZAP 90004, Low).** Shipping
  it was in the original plan, but `Cross-Origin-Resource-Policy: same-origin`
  broke NiceGUI's websocket-driven navigation in the e2e tier (the login →
  `/login/mfa` step bounced to `/login`), and COEP (`require-corp`) is riskier
  still. 90004 is a Low, so the whole set is deferred to a guarded follow-up
  (verify every subresource carries CORP under a real browser first) rather than
  shipped half-working — ZAP 90004 stays a WARN. See `docs/plans/chores.md`.
- The **headless API** path (`run_api()`): F-8 is the browser app. The API is
  JSON-only (no clickjacking/CSP surface); wiring the same middleware there is a
  possible later consistency step, noted not done.
- A user-tunable CSP string. The toggle is the escape hatch; a per-directive
  override can follow if a deploy needs it.

## Acceptance criteria

- Every web response carries the CSP, `X-Frame-Options`,
  `X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy`;
  `Strict-Transport-Security` only when `session_cookie_secure`.
- The headers are present on an `AuthMiddleware` redirect response too.
- `KALETA_SECURITY_HEADERS_ENABLED=false` disables all of them.
- A real ZAP baseline re-run against a live instance no longer WARNs for CSP
  (10038), anti-clickjacking (10020), X-Content-Type-Options (10021) or
  Permissions-Policy (10063); the UI still loads (e2e green).
- `KAL-SEC-006` is `@automated`, its covering test in `tests/integration/`;
  `scripts/spec_coverage.py` stays green.
- `./scripts/verify.sh --e2e` passes (the middleware touches every view's
  response, so the e2e tier confirms the CSP does not break the UI even though
  no file under `src/kaleta/views/` changed).

## Touchpoints

`src/kaleta/security_headers.py` (new), `src/kaleta/config/settings.py`,
`src/kaleta/main.py`, `docs/bdd.md` (KAL-SEC-006),
`tests/integration/test_security_headers.py` (new),
`docs/security/assessment-2026-10-12.md`, `docs/plans/chores.md`.

## Implementation notes

- **Pure-ASGI middleware.** `SecurityHeadersMiddleware` mirrors
  `RequestContextMiddleware`: it mutates the `http.response.start` headers via
  `MutableHeaders`, defining the `Scope`/`Receive`/`Send` aliases locally (house
  style) rather than importing `starlette.types`. Registered last in `run_web`
  via `_register_security_headers()` so it is outermost and stamps every
  response — verified on both a page and `/api/v1/health`, and on a redirect in
  the test.
- **CSP breadth is deliberate.** The policy must allow `script-src`/`style-src`
  `'unsafe-inline' 'unsafe-eval'`, `connect-src ws: wss:` and `img-src data:`
  for NiceGUI/Vue + the Socket.IO websocket. A ZAP re-run therefore now raises
  the Low "CSP: Wildcard Directive" (10055) for the `ws:`/`data:` scheme
  sources — the documented cost of a working UI, not a regression.
- **HSTS gated on `session_cookie_secure`** (the F-3 TLS signal), so a
  plain-http-behind-proxy / localhost install is never sent HSTS. Verified: no
  `Strict-Transport-Security` on the default run; present when the toggle is on.
- **Site-isolation set deferred — found by e2e.** The plan first shipped
  COOP + CORP (and deferred only COEP). But `verify.sh --e2e` caught a
  regression: with `Cross-Origin-Resource-Policy: same-origin` the MFA login
  step landed on `/login` instead of `/login/mfa`. Bisected with the
  `KALETA_SECURITY_HEADERS_ENABLED` toggle and by removing headers one group at
  a time: headers-off passed; CSP-removed still failed; COOP+CORP-removed
  passed; CSP+CORP (COOP out) failed again — so **CORP broke NiceGUI's
  websocket-driven navigation**. The whole 90004 set (COOP/COEP/CORP, a Low) is
  now deferred to a chore; a regression test asserts the two headers stay unset.
- **ZAP before/after** (`scripts/security/scan_zap.sh`, live instance): 0 FAIL
  throughout; 11 → 8 WARN, 56 → 59 PASS. Cleared: 10038 (CSP), 10020
  (anti-clickjacking), 10021 (nosniff), 10063 (Permissions-Policy). 90004
  (Spectre isolation, Low) stays WARNed — the deferred set. 10055 ("CSP:
  Wildcard Directive", Low) is the new, deliberate cost of the NiceGUI CSP.
- **Test placement.** The covering test lives in `tests/integration/`
  (`spec_coverage.py` scans integration + e2e only), driving the middleware
  through a small Starlette app over httpx — it needs no DB. Fail-on-old is
  inherent: on `main` the `kaleta.security_headers` import does not resolve.
- **e2e despite no `views/` change.** Rule 8's literal trigger (a file under
  `src/kaleta/views/`) is not hit — the middleware is a top-level module — but
  it rewrites every view's response headers, so `./scripts/verify.sh --e2e` is
  run to confirm the CSP does not break the UI (Playwright loads real pages).

## Implementation

Landed on 2026-10-21.

| SHA | Author | Date | Message |
|---|---|---|---|
| `011ff89` | Dawid (Ani) | 2026-10-21 | feat(security): set security response headers on the web app (F-8) |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/security-response-headers.md
- docs/security/assessment-2026-10-12.md
- src/kaleta/config/settings.py
- src/kaleta/main.py
- src/kaleta/security_headers.py
- tests/integration/test_security_headers.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.

**Archival note:** archived with `plan_archive.sh --fast` (acceptance criteria not re-run). PR #312 already merged with CI green. Operator-tool criteria (`scan_trivy.sh`, `scan_zap.sh`) need docker and/or a live instance and are not re-runnable CI gates; `plan_archive.sh` also mis-parses prose bullets whose first backticked token is a file path. Those criteria were verified by real runs at implementation time, recorded in `docs/security/assessment-2026-10-12.md` and this plan's Implementation notes. Feature commit: 011ff89 (PR #312).
