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

The isolation and auth design is sound. The application-level items (F-1..F-4)
were all information-disclosure / hardening defaults, now fixed. The dynamic
Slice-2 pass (Trivy) then added two infrastructure findings: the container
images ran as root (F-6, High — now fixed) and the base image carries Debian OS
CVEs (F-7, tracked — mostly no fix available upstream).

| # | Severity | Finding | Status |
|---|---|---|---|
| F-1 | Low | `/health` (unauthenticated) discloses version, migration state, suspended family ids, unlocked-keyring count | **Fixed** (`health-tiered-disclosure`, KAL-SEC-001) |
| F-2 | Low | `/api-docs` + OpenAPI JSON served unconditionally (not debug-gated) | **Fixed** (`api-docs-gated`, KAL-SEC-002) |
| F-3 | Low | Session cookie not `Secure` by default; no production warning when left off | **Fixed** (`cookie-secure-prod-warning`, KAL-SEC-003) |
| F-4 | Info | Import handler reads uploaded bytes with no independent server-side size cap (front-end limit only) | **Fixed** (`upload-byte-cap`, KAL-SEC-004) |
| F-5 | Info | Tenant schema isolation is the single control for cross-family reads (no secondary per-row predicate) | Accepted by design |
| F-6 | High | `Containerfile` / `Containerfile.full` defined no non-root `USER`, so the app ran as root in-container (Trivy DS-0002) | **Fixed** (`container-nonroot-hardening`, KAL-SEC-005) |
| F-7 | High (upstream) | Base image `python:3.13-slim` (Debian 13) carries 44 High OS-package CVEs (Trivy image scan) | Tracked — mostly no upstream fix; rebuild-on-latest mitigation |

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
| Information gathering / recon | What an unauthenticated client sees: headers, error bodies, version, docs | **F-1 (fixed)**: `/health` now discloses by tier — an unauthenticated caller gets liveness only (`health-tiered-disclosure`, KAL-SEC-001). **F-2 (fixed)**: the OpenAPI docs are now gated off in a production-shaped run (`api-docs-gated`, KAL-SEC-002). 5xx leaks nothing (`api/errors.py:73-89`). No stack traces outside debug. |
| Web application analysis | Authn on every route; authz = family isolation on `/api/v1/*` | Router-level `require_api_auth` gates all v1 routes except health; writes require a bearer token (`deps.py:143-154`). Isolation enforced by `schema_translate_map` + refuse-on-None. Static review found **no route that reads across families** (**F-5** notes it is the single control). ZAP/manual Burp pass deferred to Slice 2. |
| Vulnerability analysis / fuzzing | Input validation at Pydantic boundaries; upload parsing | Pagination capped (`page_size le=200`); search `max_length=200`. Decode never raises. **F-4 (fixed)**: the handler now enforces a server-side byte cap before reading the body (`upload-byte-cap`, KAL-SEC-004). Schema-aware fuzzing (`schemathesis`) deferred to Slice 2. |
| Database / SQL injection | Raw SQL audit; blind-index safety | Only `text()` uses are constants, bound params, or regex-validated schema identifiers (`tenant_service.py:102,110`); **no user-controlled raw SQL**. Blind-index columns maintained by an ORM `before_flush` hook and queried via ORM equality — no raw `_bidx` query. sqlmap pass deferred to Slice 2. |
| Password / brute force | Login + MFA rate limits, lockout, token revocation | 5/15-min lockout; per-user revocation watermark; `secrets.compare_digest` on token + nonce. In-process limiter is non-atomic across replicas (use Redis in prod). |
| Sniffing / TLS / cookies | Cookie flags, secrets in URLs | **F-3 (fixed)**: `session_cookie_secure` defaults `False` (deliberate for http-only installs), and a production-shaped run without `Secure` now logs a start-up warning (`cookie-secure-prod-warning`, KAL-SEC-003). `SameSite=lax`. HttpOnly via Starlette default. No PII/secrets placed in URLs. `testssl.sh` is a deployment-edge check (Caddy), out of scope for a local HTTP instance. |
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
- **Trivy** — `./scripts/security/scan_trivy.sh` (Slice 2), pinned `0.76.0`,
  gate `HIGH,CRITICAL`:
  - `fs` (reads `uv.lock`): **clean** — a second opinion that agrees with
    pip-audit. The walk skips installed virtualenvs and the `.claude`
    worktrees, so it reports the dependency *source*, not what a throwaway env
    happens to have synced.
  - `secret`: **clean** — no committed secret at or above the gate.
  - `config` (IaC / Containerfile misconfig): **F-6** — both `Containerfile`
    and `Containerfile.full` fail `DS-0002` (no non-root `USER`). The
    `deploy/k3s` Helm chart is not rendered (its `secretKey` default is empty
    by design — the app refuses the insecure default), so Trivy skips it; a
    full chart scan needs `--helm-set`.
  - `image python:3.13-slim`: **F-7** — 44 High OS-package CVEs in the Debian
    13 base (plus a few in base Python tooling). Recorded below.

### Note on the S310 noqa (NBP rate fetch)

`services/nbp_rate_service.py:55-61` fetches an https constant
(`NBP_TABLE_A_URL`). The `url` is a constructor argument defaulting to that
constant and is **not user-controlled**; if that ever changes, add a scheme
allowlist. No action now.

## Findings detail

- **F-1 (Low, FIXED) — `/health` discloses operational state.** Unauthenticated
  `GET /health` used to return app version, DB reachability, migration-pending
  flag, auth backend, unlocked-keyring session count, and **suspended family
  ids** to anyone. Version + suspended-ids aid an attacker's recon, and the
  suspended-ids are cross-family.
  *Fixed* in `health-tiered-disclosure` (plan + KAL-SEC-001): the probe now
  discloses by tier. **Public** (no credential) gets liveness only — `status`
  + `database_ok` (503 when the DB is down). **Family** (any valid family
  bearer token, or a signed-in cookie session) adds the version, the sign-in
  backend and the `migrations_pending` boolean. **Admin** — reached only by an
  instance-level credential (the `KALETA_API_TOKEN` env token, or a cookie
  session the registry confirms is an instance administrator, never the session
  nav hint) — adds the cross-family state: the pending-migration count, the
  keyring-session count and the suspended-family ids. A *family-scoped*
  credential never reaches the admin tier, so no family can read another
  family's operational state. The resolver never raises (a probe answers
  200/503, not 401).
- **F-2 (Low) — OpenAPI docs always on.** *Fixed (`api-docs-gated`,
  KAL-SEC-002).* `/api-docs` and `/api-docs/openapi.json` used to be served
  unconditionally, giving any client the full API schema. They are now mounted
  by `kaleta.api.docs.mount_api_docs` only when `settings.api_docs_enabled` — a
  flag that follows `KALETA_DEBUG` unless `KALETA_API_DOCS` overrides it — so a
  production-shaped run returns 404 for both the page and the JSON by default,
  while development is unchanged and a self-hoster can opt back in. The API
  routes and their auth are untouched.
- **F-3 (Low) — cookie not `Secure` by default.** *Fixed
  (`cookie-secure-prod-warning`, KAL-SEC-003).* `session_cookie_secure` still
  defaults `False` — a deliberate choice so http-only dev installs work — but a
  production-shaped run (debug off) that serves the cookie without `Secure` now
  logs a start-up warning (`warn_insecure_cookie_in_production`), the mirror of
  the existing debug-time warning. We **warn, not refuse**: unlike the
  placeholder `secret_key` (never valid in production), a plain-http run is
  legitimate behind a TLS-terminating reverse proxy or on a trusted LAN, and the
  app has no reliable signal that TLS is present — so the operator sets
  `KALETA_SESSION_COOKIE_SECURE=true` once TLS is in front.
- **F-4 (Info) — no server-side upload byte cap.** *Fixed (`upload-byte-cap`,
  KAL-SEC-004).* `max_file_size=50MB` was only a NiceGUI front-end limit, and
  `handle_upload` read `await e.file.read()` with no independent server-side
  cap, so a crafted POST could pressure memory. The handler now rejects an
  upload larger than `settings.max_upload_bytes` (`KALETA_MAX_UPLOAD_BYTES`,
  default 50 MiB) via `upload_exceeds_cap`, checking `FileUpload.size()`
  **before** `read()` so an oversize body never becomes an in-memory `bytes`
  object. The browser `max_file_size` now reads the same setting, so the two
  cannot drift.
- **F-5 (Info, accepted) — isolation is the single cross-family control.**
  There is no secondary per-row `family_id` predicate in API services; isolation
  rests entirely on correct tenant binding + schema separation. This is by
  design (ADR-38) and backed by the refuse-on-None guard and the integration
  isolation tests. Recorded so it is a conscious decision, not an oversight.
  *Update (`api-tenant-isolation-guard`):* because it is the single control, a
  static guard (`tests/integration/test_api_tenant_isolation_guard.py`) now
  asserts every `/api/v1` data handler opens its session through `get_session`
  (tenant-bound) and no v1 module reaches for the public/registry or a raw
  session factory — so a future route that skipped the family binding fails the
  suite. F-5 stays accepted by design, now defended.
- **F-6 (High) — container images ran as root.** *Fixed*
  (`container-nonroot-hardening`, KAL-SEC-005). Trivy `config` (DS-0002)
  reported that neither `Containerfile` nor `Containerfile.full` declared a
  non-root `USER`, so the process ran as `root` inside the container — a
  container escape then started with root. Both images now add a dedicated
  non-root user (uid/gid 10001 `app`) and `USER` down to it before `CMD`; as
  defence-in-depth the k3s `deployment.yaml` pod `securityContext` pins
  `runAsNonRoot: true` with `runAsUser`/`runAsGroup`/`fsGroup: 10001`, and the
  session volumes moved from `/root/.kaleta` to `/home/app/.kaleta`. A rebuilt
  image reports `uid=10001(app)` and a fresh `trivy config` no longer flags
  DS-0002; `tests/integration/test_container_hardening.py` guards it.
- **F-7 (High, upstream) — base-image OS CVEs.** *Tracked.* Scanning
  `python:3.13-slim` (Debian 13.7) reports 44 High OS-package CVEs in
  Debian-maintained system libraries. They were not individually assessed;
  many carry no fixed version upstream yet (the `fixed` column is empty).
  Mitigation: rebuild on the latest `python:3.13-slim` on each release so fixes
  land as Debian ships them, and consider a slimmer/distroless runtime base as
  a later hardening step. Not individually actionable now; re-checked by the
  `image` scan each pass.

## Next

Slice 2 (`docs/plans/security-assessment.md`): dynamic runner scripts against a
live or built target, a `KAL-SEC-*` regression test per confirmed finding, and
fixes for the remaining hardening items on their own branches.

- **F-1..F-4 fixed** (`health-tiered-disclosure`, `api-docs-gated`,
  `cookie-secure-prod-warning`, `upload-byte-cap`); **F-5** accepted by design
  and defended by the isolation guard.
- **Trivy runner added** (`security-trivy-scan`): `fs`/`secret`/`config`/`image`
  via `scripts/security/scan_trivy.sh`. It surfaced **F-6** (containers ran as
  root — now **fixed** by `container-nonroot-hardening`) and **F-7**
  (base-image OS CVEs — tracked).
- **F-6 fixed** (`container-nonroot-hardening`, KAL-SEC-005): both images run as
  the non-root `app` user and the k3s Deployment pins `runAsNonRoot`.
- **Still to do in Slice 2:** the **ZAP baseline** and **`schemathesis`**
  runners against a live instance. Wiring the headless checks (Trivy
  `fs`/`config`/`secret`, pip-audit) into a nightly CI job is the follow-up
  after the runners land.
