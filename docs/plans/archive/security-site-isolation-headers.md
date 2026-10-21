---
plan_id: security-site-isolation-headers
title: Ship the Spectre site-isolation response headers (F-8 follow-up)
area: security (response headers)
effort: small
status: archived
archived_at: 2026-10-21
roadmap_ref: ../../roadmap.md
---

# Ship the Spectre site-isolation response headers (F-8 follow-up)

## Intent

The F-8 fix (`security-response-headers`, KAL-SEC-006) shipped a NiceGUI-safe
CSP and the smaller hardening headers, but **deferred** the Spectre
site-isolation set — `Cross-Origin-Opener-Policy`, `Cross-Origin-Embedder-Policy`,
`Cross-Origin-Resource-Policy` (ZAP 90004, **Low**) — because, at the time,
shipping `Cross-Origin-Resource-Policy: same-origin` made the MFA login step
(`login` → `/login/mfa`) bounce back to `/login` in the e2e tier.

A systematic re-investigation (see Implementation notes) shows that blocker **no
longer reproduces**: with the full COOP + COEP + CORP set the websocket, the
service worker and the MFA navigation all work. This slice ships the three
headers and flips the regression guard, clearing ZAP 90004 in full.

## Scope

- **`src/kaleta/security_headers.py`** — add the three headers to
  `_STATIC_HEADERS`: `cross-origin-opener-policy: same-origin`,
  `cross-origin-embedder-policy: require-corp`,
  `cross-origin-resource-policy: same-origin`. Replace the deferral comment
  (lines 69-73) with a note recording the evidence that they are now safe.
- **`tests/integration/test_security_headers.py`** — flip the regression: the
  two `assert ... not in resp.headers` lines become assertions that the three
  headers **are** present with the expected values (add them to `_EXPECTED`).
- **`docs/bdd.md`** — extend KAL-SEC-006 with a line for the site-isolation
  trio (same scenario, same feature: hardening headers — no new KAL id).
- **`docs/security/assessment-2026-10-12.md`** — mark ZAP 90004 cleared (no
  longer a residual WARN); update the F-8 writeup and the `Next` note.
- **`docs/plans/chores.md`** — tick off the F-8 site-isolation follow-up item.

## Not in scope

- Any change to the CSP, the smaller headers, or the HSTS gate (F-8, shipped).
- The service worker, the Socket.IO transport config, or NiceGUI itself — the
  investigation confirmed they need no change.
- Hosted-mode auth provider flows (Supabase email links) — these are top-level
  navigations, not embedded cross-origin subresources, so COEP does not touch
  them; nothing to change, noted for completeness. **Caveat not exercised by the
  e2e:** `COOP: same-origin` severs `window.opener`, so a *popup*-based OAuth/SSO
  flow (if hosted mode ever adds one) would break and must revisit this; the e2e
  runs plain local mode with no popup provider and no TLS/reverse proxy.

## Acceptance criteria

- `grep -q 'cross-origin-opener-policy' src/kaleta/security_headers.py`
- `grep -q 'cross-origin-embedder-policy' src/kaleta/security_headers.py`
- `grep -q 'cross-origin-resource-policy' src/kaleta/security_headers.py`
- `uv run pytest tests/integration/test_security_headers.py -q`
- `grep -q 'site-isolation\|Cross-Origin-Opener' docs/bdd.md`
- `./scripts/verify.sh --e2e` passes (the change stamps headers on every view
  response — rule 8; the MFA e2e is the guard that caught the original issue).

## Touchpoints

`src/kaleta/security_headers.py`, `tests/integration/test_security_headers.py`,
`docs/bdd.md`, `docs/security/assessment-2026-10-12.md`, `docs/plans/chores.md`.

## Implementation notes

- **Why the deferral was lifted — the investigation (2026-10-21).** The original
  deferral assumed `Cross-Origin-Resource-Policy: same-origin` was incompatible
  with NiceGUI's websocket navigation. Re-tested under a real Chromium
  (Playwright) against a live instance:
  - **CORP alone**: a browser probe (cold load, service-worker-active reload,
    SW-active navigation) showed the Socket.IO websocket connected throughout,
    the SW re-served every `/_nicegui/` asset 200, zero failed requests, zero
    console errors. The MFA e2e (`test_mfa.py::test_two_factor_authentication`)
    passed **3/3**.
  - **Full COOP + COEP + CORP** (COEP `require-corp`, the strict one): the same
    probe was clean — socket connected, 0 failures, **0 COEP violations** in the
    console — and the MFA e2e passed **3/3**.
  - **Why COEP `require-corp` blocks nothing**: the app loads only same-origin
    subresources (the CSP already pins `default-src 'self'`), and the middleware
    stamps CORP on every response, so every subresource carries CORP. COEP only
    enforces at the resource level what the CSP already requires; the posture is
    consistent, not newly restrictive.
  - **Root cause of the original failure**: not reproducible in the current tree.
    Most likely a flaky e2e mis-attributed to CORP in a one-shot bisection (the
    MFA/navigation e2e has documented flakiness in `chores.md`), or a race since
    fixed (NiceGUI moved to 3.18.0; session/nav code changed since 2026-10-12).
    Either way the blocker is gone; the full `--e2e` MFA test is the standing
    guard if a residual race ever resurfaces.
- **Tooling for the probe**: a throwaway Playwright script (not committed) that
  captured console, failed requests, service-worker-served responses and socket
  state across cold/SW-active loads.

## Implementation

Landed on 2026-10-21.

| SHA | Author | Date | Message |
|---|---|---|---|
| `da2626d` | Dawid Adamski | 2026-10-21 | Merge pull request #320 from DawidAdamski/feat/security-site-isolation-headers |
| `4416ff0` | Dawid | 2026-10-21 | feat(security): ship the Spectre site-isolation response headers (F-8) |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/security-site-isolation-headers.md
- docs/security/assessment-2026-10-12.md
- src/kaleta/security_headers.py
- tests/integration/test_security_headers.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `grep -q 'cross-origin-opener-policy' src/kaleta/security_headers.py` | 0 |
| `grep -q 'cross-origin-embedder-policy' src/kaleta/security_headers.py` | 0 |
| `grep -q 'cross-origin-resource-policy' src/kaleta/security_headers.py` | 0 |
| `uv run pytest tests/integration/test_security_headers.py -q` | 0 (4 passed) |
| `grep -q 'site-isolation\|Cross-Origin-Opener' docs/bdd.md` | 0 |
| `./scripts/verify.sh --e2e` | not re-run; verified green at implementation time (PR #320) |

**Notes:** Merge `da2626d`, implementation commit `4416ff0`. All touchpoints were changed by the merge.
