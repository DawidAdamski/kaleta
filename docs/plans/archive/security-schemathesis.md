---
plan_id: security-schemathesis
title: schemathesis API-fuzzing runner for the security assessment (Slice 2b)
area: security (dynamic scanners)
effort: small
status: archived
archived_at: 2026-10-21
roadmap_ref: ../../roadmap.md
---

# schemathesis API-fuzzing runner for the security assessment (Slice 2b)

## Intent

`docs/plans/security-assessment.md` Slice 2 wires the dynamic scanners that need
a live instance. The ZAP baseline landed (Slice 2a); this slice delivers the
second: a **schemathesis** runner that property-based-fuzzes the API against its
own OpenAPI schema (`/api-docs/openapi.json`). It generates edge-case inputs for
every `/api/v1` operation and checks the responses — the main security value is
`not_a_server_error`: no fuzzed input should crash a handler into a 5xx.

Tooling-only slice, mirroring the Trivy and ZAP runners: the script + the dev
dependency + docs, plus a triage of the first run into the assessment. Any
confirmed finding is fixed on its own later branch with a `KAL-SEC-*` test.

## Scope

- **`pyproject.toml`** — add `schemathesis>=4.0` to the `dev` dependency group
  (a Python tool, run via `uv run` like `pip-audit`/`audit_deps.sh`).
- **`scripts/security/scan_schemathesis.sh`** (new, executable) — wrap
  `schemathesis run` against a target (default `http://localhost:8080`): build
  the schema URL (`<base>/api-docs/openapi.json`), pin `--url <base>`, a bounded
  `--max-examples`, and an optional bearer. Env-overridable, matching
  `scan_zap.sh`'s shape. Exit code is schemathesis's own (0 pass / 1 check
  failed / 2 could-not-run).
- **`docs/security/README.md`** — add schemathesis to the "Dynamic runners
  (scripted)" section; drop it from the "Manual" table.
- **`docs/security/assessment-2026-10-12.md`** — triage the first run under the
  Vulnerability-analysis/fuzzing category and the `Next` section.
- **`docs/plans/security-assessment.md`** — Slice-2 progress note.

## The auth boundary (why the default is `not_a_server_error`)

Every `/api/v1` route except health is behind `require_api_auth`, so an
unauthenticated fuzz gets a well-formed 401 before the handler — useful to prove
the auth layer itself never 5xxes on a malformed request, but it cannot reach
handler/validation logic, and `status_code_conformance` would just flag the
(undocumented) 401s as noise. So:

- **Default checks: `not_a_server_error`** — a crisp, low-noise gate meaningful
  with or without a token (nothing fuzzed should 5xx).
- **Deeper, authenticated fuzz is operator-run**: set `ST_BEARER` (a real
  bearer, from a seeded/staging instance with an unlocked keyring) and
  `ST_CHECKS=all` to exercise conformance against the real handlers. Documented,
  not bootstrapped here (a token needs an active family + unlocked keyring,
  ADR-35 — out of a scanner slice's scope).

## Not in scope

- Bootstrapping a family/admin/token to run the full authenticated conformance
  fuzz in CI — documented as an operator step.
- Wiring the headless checks into nightly CI (the follow-up after both runners
  land; schemathesis needs a live instance, so it is not a server-less CI check).
- Fixing any finding the run surfaces — each gets its own branch + `KAL-SEC-*`.

## Acceptance criteria

- `./scripts/security/scan_schemathesis.sh` runs `schemathesis run` against a
  live instance (API docs enabled), fuzzing every documented operation, and
  exits with schemathesis's status (verified by a real run).
- The runner is `scripts/security/` executable (mode 100755), self-documents its
  usage + env overrides, and takes an optional `ST_BEARER` / `ST_CHECKS`.
- `docs/security/README.md` lists the scripted command; the assessment records
  the first run's result.
- `./scripts/verify.sh` passes (no `src/` change → short gate).

## Touchpoints

`pyproject.toml`, `uv.lock`, `scripts/security/scan_schemathesis.sh` (new),
`.gitignore` (ignore the `.schemathesis/` run-state dir),
`docs/security/README.md`, `docs/security/assessment-2026-10-12.md`,
`docs/plans/security-assessment.md`.

## Implementation notes

- **Runner shape.** `scan_schemathesis.sh` mirrors `audit_deps.sh`: a Python
  dev tool via `uv run --no-sync schemathesis run`. It builds the schema URL
  from the target (`<base>/api-docs/openapi.json`), pins `--url <base>`, bounds
  `--max-examples`, and appends `--header "Authorization: Bearer $ST_BEARER"`
  when `ST_BEARER` is set. Exit code is schemathesis's own (0 / 1 / 2).
- **schemathesis 4.32.2** (4.x CLI: `run SCHEMA`, `-u/--url`, `-c/--checks`,
  `-n/--max-examples`, `-H/--header`, `--report json --report-dir`).
- **First run** (`not_a_server_error`, unauthenticated, max-examples 50, API
  docs on): **52 operations, 4831 generated cases, all passed; exit 0.**
  schemathesis also warned "Authentication failed: 51 operations returned only
  401/403" — exactly the auth gate (every `/api/v1` route but health). So the
  negative result is meaningful: no fuzzed input 5xxes the auth layer or the
  public surface. Triaged into `assessment-2026-10-12.md`; no new finding.
- **Why not the full conformance fuzz here.** Reaching handler logic needs a
  bearer, which needs an active family + unlocked keyring (ADR-35) — not
  something a scanner slice bootstraps. The runner takes `ST_BEARER` +
  `ST_CHECKS=all` so an operator runs the deep conformance fuzz against a
  seeded/staging instance; documented, not automated.
- **Tooling-only slice.** Like Trivy/ZAP, no new `KAL-SEC-*` scenario (a scanner
  script is not user-facing app behaviour); short verify gate (no `src/` change).

## Implementation

Landed on 2026-10-21 (PR #313).

| SHA | Author | Date | Message |
|---|---|---|---|
| `35d8dd1` | Dawid Adamski | 2026-10-21 | Merge pull request #313 from DawidAdamski/feat/security-schemathesis |

**Files changed:**
- .gitignore
- docs/plans/security-assessment.md
- docs/plans/security-schemathesis.md
- docs/security/assessment-2026-10-12.md
- docs/security/README.md
- pyproject.toml
- scripts/security/scan_schemathesis.sh
- uv.lock

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `./scripts/security/scan_schemathesis.sh` | 0 |
| `./scripts/verify.sh` | 0 |

Note: `plan_archive.sh` mis-parsed the prose bullet starting with `docs/security/README.md` as a command (exit 126), so it was run with --fast and the two real commands above were run by hand against a live instance.

**Notes:** Feature commit is 91f74d5 ("feat(security): add a schemathesis API-fuzzing runner (Slice 2b)"), merged by 35d8dd1; the changed files match the plan's Touchpoints.
