---
plan_id: security-nightly-ci
title: Wire the server-less security checks into a nightly CI job
area: security (CI)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Wire the server-less security checks into a nightly CI job

## Intent

Slice 2 of `docs/plans/security-assessment.md` added the headless security
runners (Trivy, ZAP, schemathesis) and `audit_deps.sh` (pip-audit). Two of
them need no live instance and run fully headless: **`audit_deps.sh`**
(dependency advisories) and **`scan_trivy.sh`** in its `fs`/`config`/`secret`
modes (= `all`). Nothing runs them automatically yet, so a new advisory or a
newly-introduced misconfiguration/secret is only caught when someone runs the
script by hand. This slice wires exactly those two server-less checks into a
**scheduled nightly GitHub Actions job** — catching regressions without
touching PR latency. This is the last open Slice-2 item
(`security-assessment.md`, open question 1; `docs/plans/chores.md`).

## Scope

- **`.github/workflows/security-nightly.yml`** (new) — a dedicated workflow,
  `schedule:` (nightly cron, offset from `ci.yml`'s `17 3 * * *`) plus
  `workflow_dispatch:` for on-demand runs. Two independent jobs so each
  surfaces its own pass/fail:
  - `audit-deps` — `uv sync --group dev`, then `./scripts/security/audit_deps.sh`.
  - `trivy` — `./scripts/security/scan_trivy.sh all` (the script falls back to
    the pinned `aquasec/trivy` container via Docker, which `ubuntu-latest` has;
    no extra setup action needed). Cache `~/.cache/trivy` so the vuln DB
    download is not repeated every night.
  Reuse the existing pinned actions (`actions/checkout@v7`,
  `astral-sh/setup-uv@v7`) to match `ci.yml`.
- **`docs/security/README.md`** — note that the two server-less checks also run
  nightly in CI (the scripts stay the single source of truth; the workflow only
  invokes them).
- **`docs/plans/security-assessment.md`** — Slice-2 progress note: nightly CI
  wired; mark open question 1 resolved for the server-less checks.
- **`docs/plans/chores.md`** — tick off the "Wire the headless security checks
  into nightly CI" item.

## Not in scope

- The scanners that need a live instance (**ZAP**, **schemathesis**): they stay
  operator/pre-release runs — a nightly job would have to boot the app (and, for
  the authenticated fuzz, seed a family + unlock the keyring). Out of this
  slice; documented as such.
- The `scan_trivy.sh image` mode (needs a built image; the `docker.yml` image
  build is where an image scan would later hook in).
- Any failure-notification wiring beyond GitHub's own red-run signal
  (Slack/email alerts, issue auto-filing) — a later chore if wanted.
- A dedicated Kali/slim scanner image (open question 2) — the scripts' existing
  binary-or-container runner covers CI; no new image here.

## Design decision — dedicated workflow vs. a job in `ci.yml`

A separate `security-nightly.yml` over another job in `ci.yml`: the security
nightly has a different cadence and owner-signal than the test matrix, a red
security run should be legible on its own rather than buried in a CI matrix,
and `ci.yml` stays about "does the code build and pass tests". `ci.yml` already
carries a nightly `schedule`; this slice does not change it.

## Acceptance criteria

- `test -f .github/workflows/security-nightly.yml`
- `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/security-nightly.yml'))"`
- `grep -q 'audit_deps.sh' .github/workflows/security-nightly.yml`
- `grep -q 'scan_trivy.sh all' .github/workflows/security-nightly.yml`
- `grep -q 'schedule:' .github/workflows/security-nightly.yml`
- `grep -q 'workflow_dispatch:' .github/workflows/security-nightly.yml`
- `grep -q 'nightly' docs/security/README.md`
- `./scripts/verify.sh` passes (no `src/` change → short gate).
- [manual] `./scripts/security/audit_deps.sh` and
  `./scripts/security/scan_trivy.sh all` are green — verified by a real run
  during implementation (recorded in Implementation notes) and run nightly by
  the workflow itself. Marked `[manual]` because both need an operator
  environment (network for pip-audit, Docker for Trivy) that the archiver gate
  does not provide; they are not re-runnable from a bare checkout.

## Touchpoints

`.github/workflows/security-nightly.yml` (new), `docs/security/README.md`,
`docs/plans/security-assessment.md`, `docs/plans/chores.md`.

## Implementation notes

- **Tooling-only slice.** Like the Trivy/ZAP/schemathesis runner slices, no new
  `KAL-SEC-*` scenario (a CI workflow is not user-facing app behaviour); short
  verify gate (no `src/` change).
- **Why only these two checks.** ZAP and schemathesis need a live instance; the
  nightly job stays server-less to avoid booting + seeding the app. `scan_trivy.sh
  all` = `fs` + `config` + `secret` (the server-less modes); `image` needs a
  built image and belongs with the image build.
- **Real run of the two checks (the `[manual]` criterion), 2026-10-21:**
  - `./scripts/security/audit_deps.sh` → exit 0, "No known vulnerabilities
    found" (after `uv sync --group dev` against current `main`). NB a stale
    local `.venv` first reported the certifi/pillow CVEs that dependabot #314 /
    #315 had just fixed in the lockfile — a neat demonstration of why the
    nightly job is worth having: it catches exactly that drift.
  - `./scripts/security/scan_trivy.sh all` → exit 0; `fs`, `config` and `secret`
    all "Clean (no security findings detected)". The `config` step logs a WARN
    skipping the `deploy/k3s` Helm chart — expected and documented
    (`docs/security/README.md`): Helm templates are not valid YAML until
    rendered, so Trivy skips them; the plain compose files and `Containerfile*`
    are covered.
- **Trivy in CI uses Docker.** `ubuntu-latest` ships Docker, and `scan_trivy.sh`
  falls back to the pinned `aquasec/trivy` container when no local binary
  exists, so no `setup-trivy`/marketplace action is needed. The vuln DB is
  cached under `~/.cache/trivy` via `actions/cache`.
