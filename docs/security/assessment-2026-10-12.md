# Security assessment — 2026-10-12

A security engineering pass against our own Kaleta instance, framed as a walk
through Kali Linux's tool categories used as a *checklist of attack surfaces*.
This is authorised testing of software we own, run against a local instance we
control. It is an engineering pass, not a formal pentest certification.

- **Plan**: `docs/plans/security-assessment.md` (Slice 1 — recon + static pass).
- **Instance**: local checkout at commit `30c0fb7` (main), `KALETA_DEBUG`
  unset, `auth_backend=local`, PostgreSQL 16.
- **Method**: static source review (the surface map below), the two headless
  checks (`docs/security/README.md`), and a static authz review of the API.
  Dynamic scanners (ZAP, schemathesis, sqlmap) are scoped to Slice 2.

Code citations are `file:line` at the reviewed commit.

## Summary of findings

No High or Critical findings. The isolation and auth design is sound; the open
items are information-disclosure and hardening defaults, all Low/Info.

| # | Severity | Finding | Status |
|---|---|---|---|
| F-1 | Low | `/health` (unauthenticated) discloses version, migration state, suspended family ids, unlocked-keyring count | Tracked |
| F-2 | Low | `/api-docs` + OpenAPI JSON served unconditionally (not debug-gated) | Tracked |
| F-3 | Low | Session cookie not `Secure` by default; no production warning when left off | Tracked |
| F-4 | Info | Import handler reads uploaded bytes with no independent server-side size cap (front-end limit only) | Tracked |
| F-5 | Info | Tenant schema isolation is the single control for cross-family reads (no secondary per-row predicate) | Accepted by design |

## Surface map

What the app exposes (grounded in source):

- **HTTP API** — `/api/v1/*` assembled in `api/v1/__init__.py:19` under a
  router-level `Depends(require_api_auth)`; **every v1 route except health is
  auth-gated**. State-changing calls (`POST`/`PUT`/`DELETE`) require a **bearer
  token** — cookie-session auth is accepted only for safe methods
  (`api/deps.py:143-154`), which removes the CSRF surface for writes.
- **Public HTTP** — `GET /api/v1/health` + alias `GET /health`
  (`api/v1/health.py:35,54`); `GET /auth/session/rotate` (nonce-guarded,
  `auth/routes.py:36`); `GET /api-docs` + `/api-docs/openapi.json`
  (`main.py:72-81`).
- **NiceGUI pages** — public: `/login`, `/login/mfa`, `/create-account`,
  `/reset-password`, `/join`, `/auth/magic`; everything else behind
  `AuthMiddleware`. `/admin` re-checks admin server-side against the registry
  (`auth/admin.py:113-118`); the session `instance_admin` flag is only a nav
  hint.
- **Auth** — server-side session in `app.storage.user` keyed by signed cookie
  `kaleta_session` (`auth/session.py:33`); absolute TTL 72h + idle 12h;
  login/logout rotate the storage id via single-use nonce (session-fixation
  defense); per-user revocation watermark. Bearer tokens `kt_<tenantId>_<secret>`,
  SHA-256 hashed and compared with `secrets.compare_digest`
  (`services/api_token_service.py`). Passwords argon2. MFA TOTP + recovery
  codes; minting a token requires MFA step-up.
- **Rate limiting** — 5 failures / 15-min lock; password limiter keyed by
  client IP, MFA limiter by user id (`auth/login_rate_limit.py:188-246`).
  Redis-backed when `KALETA_REDIS_URL` set, else in-process (not atomic across
  replicas — noted in source).
- **Tenant isolation** — one engine, per-request `schema_translate_map={None:
  schema}` (`db/session.py:100-115`); opening a session with no tenant bound
  **raises** rather than falling back (`tenant_context.py:45-51`). Schema names
  are `t_` + 12 hex from `secrets`, regex-validated, never user-derived.
- **Import** — `ui.upload(max_files=20, max_file_size=50MB)`
  (`views/import_view/upload_section.py:28-37`); parser handles CSV / mBank /
  Wise / ZIP / XLSX; decode never raises (`services/import_service.py:55-72`).
- **Errors** — uniform `{"error":{code,message,event_id?}}`; 5xx returns a
  correlation id, **no stack trace or exception detail** to the client
  (`api/errors.py:73-89`).
- **Config/secrets** — `secret_key` default is insecure but the app **refuses
  to start** in non-debug with it (`config/settings.py:282-290`); field
  encryption `off` only allowed under debug; `db_url` must be
  `postgresql+asyncpg://`.

## Kali category walk

Each category is marked **applies** (with the concrete check and result) or
**n/a** (with one line why), so the walk is complete rather than cherry-picked.

### Applies

| Category | Check | Result |
|---|---|---|
| Information gathering / recon | What an unauthenticated client sees: headers, error bodies, version, docs | **F-1, F-2**: `/health` and always-on OpenAPI docs leak version + operational state. 5xx leaks nothing (`api/errors.py:73-89`). No stack traces outside debug. |
| Web application analysis | Authn on every route; authz = family isolation on `/api/v1/*` | Router-level `require_api_auth` gates all v1 routes except health; writes require a bearer token (`deps.py:143-154`). Isolation enforced by `schema_translate_map` + refuse-on-None. Static review found **no route that reads across families** (**F-5** notes it is the single control). ZAP/manual Burp pass deferred to Slice 2. |
| Vulnerability analysis / fuzzing | Input validation at Pydantic boundaries; upload parsing | Pagination capped (`page_size le=200`); search `max_length=200`. Decode never raises. **F-4**: server-side handler reads uploaded bytes with only the front-end 50 MB limit — no independent byte cap. Schema-aware fuzzing (`schemathesis`) deferred to Slice 2. |
| Database / SQL injection | Raw SQL audit; blind-index safety | Only `text()` uses are constants, bound params, or regex-validated schema identifiers (`tenant_service.py:102,110`); **no user-controlled raw SQL**. Blind-index columns maintained by an ORM `before_flush` hook and queried via ORM equality — no raw `_bidx` query. sqlmap pass deferred to Slice 2. |
| Password / brute force | Login + MFA rate limits, lockout, token revocation | 5/15-min lockout; per-user revocation watermark; `secrets.compare_digest` on token + nonce. In-process limiter is non-atomic across replicas (use Redis in prod). |
| Sniffing / TLS / cookies | Cookie flags, secrets in URLs | **F-3**: `session_cookie_secure` defaults `False` (deliberate for http-only installs, but no prod warning when off). `SameSite=lax`. HttpOnly via Starlette default. No PII/secrets placed in URLs. `testssl.sh` is a deployment-edge check (Caddy), out of scope for a local HTTP instance. |
| Reporting | Record findings | This document; headless checks under `scripts/security/`. |

### Not applicable

- **Wireless / Bluetooth / RF** — Kaleta is a web app; no radio surface.
- **Hardware / embedded** — no device firmware.
- **Social engineering** — a people-process concern, not a code check.
- **Exploitation frameworks (Metasploit, etc.)** — aimed at exploiting known
  CVEs in third-party services; our dependency audit (below) covers the "known
  CVE" angle for code we ship, and we do not test third-party infrastructure.
- **Post-exploitation / C2 / password cracking at scale** — offensive tooling
  against third parties; out of scope by the plan.
- **Forensics / reverse engineering** — not an attack surface of a running
  instance.

## Headless checks run

- **Dependency advisories** — `./scripts/security/audit_deps.sh` (pip-audit,
  OSV/PyPI): **no known vulnerabilities** across the third-party tree. The
  local editable `kaleta` package is skipped (not on PyPI).
- **Static security lint** — `uv run ruff check src/ --select S` (bandit-derived):
  **clean**. Five `# noqa: S…`, each with an explanatory comment:
  three `S105` on non-password constants, two `S310` on `urllib.urlopen` in the
  NBP rate fetch where the URL is an https constant (see note below).

### Note on the S310 noqa (NBP rate fetch)

`services/nbp_rate_service.py:55-61` fetches an https constant
(`NBP_TABLE_A_URL`). The `url` is a constructor argument defaulting to that
constant and is **not user-controlled**; if that ever changes, add a scheme
allowlist. No action now.

## Findings detail

- **F-1 (Low) — `/health` discloses operational state.** Unauthenticated
  `GET /health` returns app version, DB reachability, migration-pending flag,
  auth backend, unlocked-keyring session count, and **suspended family ids**
  (`api/v1/health.py:35-51`). Version + suspended-ids aid an attacker's recon.
  *Remediation options (Slice 2):* trim the body for unauthenticated callers
  (health boolean only), move the detailed payload behind auth, or drop the
  suspended-ids list. Track before public deploy.
- **F-2 (Low) — OpenAPI docs always on.** `/api-docs` and
  `/api-docs/openapi.json` are served unconditionally (`main.py:72-81`), giving
  any client the full API schema. *Remediation:* gate behind `KALETA_DEBUG` or
  auth in production. Low because the API is already fully auth-gated; this only
  eases enumeration.
- **F-3 (Low) — cookie not `Secure` by default.** `session_cookie_secure`
  defaults `False` (`config/settings.py:68`) — a deliberate choice so http-only
  dev installs work, documented in the source comment. The gap: there is a
  debug-time warning when secure is *on*, but **no warning when it is left off
  in a non-debug (production-shaped) run** (verified by grep —
  `warn_secure_cookie_in_debug` is the only such warning). *Remediation:* warn (or refuse) when
  a non-debug instance serves the cookie without `Secure`, mirroring the
  `secret_key` guard.
- **F-4 (Info) — no server-side upload byte cap.** `max_file_size=50MB` is a
  NiceGUI front-end limit; `handle_upload` reads `await e.file.read()` into
  memory with no independent server-side cap (`views/import_view/page.py:388`).
  A crafted large body could pressure memory. *Remediation (Slice 2):* enforce a
  byte cap in the handler and/or a row cap in the parser.
- **F-5 (Info, accepted) — isolation is the single cross-family control.**
  There is no secondary per-row `family_id` predicate in API services; isolation
  rests entirely on correct tenant binding + schema separation. This is by
  design (ADR-38) and backed by the refuse-on-None guard and the integration
  isolation tests. Recorded so it is a conscious decision, not an oversight.

## Next

Slice 2 (`docs/plans/security-assessment.md`): dynamic runner scripts (ZAP
baseline, `schemathesis` against the OpenAPI doc) against a live instance, a
`KAL-SEC-*` regression test per confirmed finding, and fixes for F-1..F-4 on
their own branches.
