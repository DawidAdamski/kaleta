---
plan_id: security-assessment
title: Security assessment of Kaleta — a Kali toolbox walk against our own instance
area: security
effort: large
status: draft
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

## Open questions

- Run the scanners in CI on every PR, nightly, or by hand before a release? Default:
  nightly for the cheap headless ones (ZAP baseline, advisory audit), by hand for the rest,
  so PR latency is untouched.
- Use a dedicated Kali container as the runner, or install the few tools we actually use
  into a slim image? Default: a slim image with the chosen tools — reproducible in CI and
  smaller — with Kali named as the reference checklist, not a runtime dependency.
- How to handle a finding in a dependency we cannot upgrade yet? Default: record severity,
  pin a mitigation, and track it; do not silence the advisory.
