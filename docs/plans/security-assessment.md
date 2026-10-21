---
plan_id: security-assessment
title: Security assessment of Kaleta — a Kali toolbox walk against our own instance
area: security
effort: large
status: in-progress
roadmap_ref: ../roadmap.md
---

# Security assessment of Kaleta — a Kali toolbox walk against our own instance

## Intent

Before a public deployment, convince ourselves Kaleta has no obvious security holes. The
owner asked to "go through the tools in Kali Linux and decide, for each, whether it can
test our app" — i.e. use Kali's categorised toolset as a *checklist of attack surfaces*,
map each relevant category to a concrete check against **our own** instance, run the ones
that fit a NiceGUI/FastAPI/PostgreSQL app, and record the findings. This is authorised
testing of software we own, on a local or staging instance we control — never against
anyone else's systems, and never a tool built for breaking into third parties.

## Scope

- **Surface map first.** List what Kaleta exposes: the FastAPI/NiceGUI HTTP surface
  (`/api/v1/*`, the websocket, auth routes, `/join`, `/admin`), the session cookie and
  bearer tokens, the per-family schema isolation and encryption (ADR-35/38), file upload
  (import), the container and its config/secrets, and the dependency tree.
- **Kali categories → our checks.** Walk Kali's menu categories and, for each, say whether
  it applies and what the concrete check is. Expected mapping (the ones that fit):
  - *Web application analysis* — OWASP ZAP / Nikto baseline scan of the app; Burp-style
    manual review of authz on every `/api/v1` route (a member of one family must never
    read another's rows — the isolation tests already assert this; confirm over HTTP).
  - *Vulnerability analysis / fuzzing* — schema-aware fuzzing of the API (e.g. `schemathesis`
    against the OpenAPI doc), input validation on every Pydantic boundary, upload fuzzing of
    the import parser.
  - *Database* — SQL-injection probes (sqlmap) against every parameter; confirm the ORM and
    `schema_translate_map` leave no raw-SQL hole, and that blind indexes do not leak.
  - *Password / brute force* — the login and MFA rate limits (hydra-style), session fixation
    and rotation (the session-hardening plans), token revocation.
  - *Sniffing / TLS* — cookie flags (HttpOnly, Secure, SameSite), TLS config at the Caddy
    edge, no secrets or PII in URLs (the privacy rule), testssl.sh against the edge.
  - *Information gathering / recon* — what an unauthenticated scrape sees; error messages,
    headers, version disclosure, the demo instance.
  - *Reporting* — findings into this plan and `docs/security/assessment-<date>.md`.
  - Categories that do **not** apply (wireless, RF, hardware, social engineering, exploitation
    frameworks aimed at third parties) are listed as "not applicable" with one line each, so
    the walk is complete rather than cherry-picked.
- **Run what fits in CI-sized form.** Where a check can run headless against the e2e/staging
  instance (ZAP baseline, `schemathesis`, dependency audit `pip-audit`/`uv` advisory check,
  `bandit` via ruff's `S` rules already in the suite), wire it as a script under
  `scripts/security/` and document how to run the manual ones.
- **Fix or file.** Each finding is either fixed on its own branch (with a `KAL-SEC-*`
  regression test where it makes sense) or recorded with a severity and a plan.

## Not in scope

- Testing anything we do not own or host. No scans of Supabase's own infrastructure, the
  hosting provider, or any third-party endpoint — only our app and our containers.
- Turning Kaleta into a security-testing tool. We *use* scanners against ourselves; we add
  none to the product.
- A formal pentest certification; this is an engineering pass, and a professional audit may
  follow before launch.

## Acceptance criteria

- `docs/security/assessment-<date>.md` exists: the full category walk (applies / check /
  result / not-applicable), with every High or Critical finding either fixed or tracked.
- `scripts/security/` holds the headless checks, runnable against a local instance, and
  `docs/security/README.md` says how to run the manual ones.
- `uv run python scripts/spec_coverage.py` — any `KAL-SEC-*` regression tests referenced.
- The dependency advisory check passes (no known-vulnerable pinned dependency), or each
  exception is justified in the report.

## Touchpoints

`scripts/security/*` (new), `docs/security/*` (new), `docs/review-checklist.md` (a security
line), `.github/workflows/ci.yml` (optional: the headless checks on a schedule),
`docs/bdd.md` (`KAL-SEC-*` if any behaviour changes), `pyproject.toml` (dev tooling).

## Implementation notes

### Delivery in slices

This is a `large` plan; it ships in single-purpose PRs rather than one diff:

- **Slice 1 — recon + static pass (this PR).** The surface map, the full Kali
  category walk (applies / check / result / not-applicable) in
  `docs/security/assessment-2026-10-12.md`, the two headless checks that run
  with no server (`scripts/security/audit_deps.sh` for dependency advisories,
  and ruff's `S` family already in `verify.sh`), a static authz review of the
  `/api/v1` routes, and `docs/security/README.md` describing the manual/dynamic
  checks. Dev tooling: `pip-audit` added to the dev group.
- **Slice 2 — dynamic runners (later).** Headless runner scripts for the
  checks that need a live instance (ZAP baseline, `schemathesis` against the
  OpenAPI doc), wired for a local/staging target and optionally a nightly CI
  job. Any confirmed finding gets a `KAL-SEC-*` regression test and a fix
  branch.

### Decisions (Slice 1)

- **Dependency advisory tool: `pip-audit`** (open question 3). `uv` has no
  built-in advisory audit yet, so `pip-audit` (OSV/PyPI database) is added to
  the dev group and wrapped by `scripts/security/audit_deps.sh`
  (`--skip-editable` drops the local `kaleta` package, which is not on PyPI).
  First run: **no known vulnerabilities**.
- **Static security lint reuses ruff's `S` family** rather than adding a second
  bandit install — the rules are the same checks and already run in
  `verify.sh`. Clean, with five justified `# noqa: S…` (all carrying an
  explanatory comment).
- **Cadence** (open question 1): the two cheap headless checks are release/CI
  candidates; the dynamic scanners stay manual-before-release. Wiring a nightly
  job is deferred to Slice 2 so PR latency is untouched now.

### Progress (Slice 2)

- **Trivy runner landed** (`security-trivy-scan`): `scripts/security/scan_trivy.sh`
  with `fs` / `config` / `secret` / `image` modes (local binary or the pinned
  container image). First run surfaced **F-6** (containers ran as root, High)
  and **F-7** (base-image OS CVEs — tracked); fs/secret clean.
- **F-6 fixed** (`container-nonroot-hardening`, KAL-SEC-005, PR #309): both
  images run as the non-root `app` user (uid/gid 10001) and the k3s Deployment
  pins `runAsNonRoot`; a rebuilt image no longer trips Trivy DS-0002.
- **ZAP baseline runner added** (`security-zap-baseline`, Slice 2a):
  `scripts/security/scan_zap.sh`, a passive scan against a live instance via the
  pinned ZAP container. First run (0 FAIL / 11 WARN / 56 PASS) surfaced **F-8**
  (no security response headers, Medium).
- **F-8 fixed** (`security-response-headers`, KAL-SEC-006): a response-headers
  middleware stamps a NiceGUI-safe CSP + the smaller headers; a ZAP re-run
  clears them. The Spectre site-isolation set (90004, Low) was deferred (CORP
  broke the websocket).
- **schemathesis runner added** (`security-schemathesis`, Slice 2b):
  `scripts/security/scan_schemathesis.sh` fuzzes the OpenAPI schema against a
  live instance. First run clean (52 ops / 4831 cases, 0 server errors; 51 ops
  auth-gated). The authenticated conformance fuzz is operator-run (needs a
  bearer).
- **Nightly CI wired** (`security-nightly-ci`): a dedicated
  `.github/workflows/security-nightly.yml` (scheduled + `workflow_dispatch`)
  runs the two server-less checks — `audit_deps.sh` and `scan_trivy.sh all` —
  each as its own job, invoking the scripts (still the single source of truth).
  The live-instance runners (ZAP, schemathesis) stay operator/pre-release. This
  closes Slice 2.

## Open questions

- Run the scanners in CI on every PR, nightly, or by hand before a release? Default:
  nightly for the cheap headless ones (ZAP baseline, advisory audit), by hand for the rest,
  so PR latency is untouched. **Resolved (`security-nightly-ci`):** the two
  *server-less* checks (`audit_deps.sh`, `scan_trivy.sh all`) run nightly in
  `security-nightly.yml`; ZAP/schemathesis need a live instance and stay manual
  (booting + seeding the app in CI is out of scope for now).
- Use a dedicated Kali container as the runner, or install the few tools we actually use
  into a slim image? Default: a slim image with the chosen tools — reproducible in CI and
  smaller — with Kali named as the reference checklist, not a runtime dependency.
- How to handle a finding in a dependency we cannot upgrade yet? Default: record severity,
  pin a mitigation, and track it; do not silence the advisory.
