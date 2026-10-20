---
plan_id: security-trivy-scan
title: Add Trivy as a headless scanner — image CVEs, IaC misconfig, secrets
area: security (tooling)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Add Trivy as a headless scanner — image CVEs, IaC misconfig, secrets

## Intent

`scripts/security/audit_deps.sh` (pip-audit) only sees **Python package
advisories**. It cannot see the OS layer of our container image, a
misconfiguration in a deploy manifest, or a secret committed by accident.
Trivy closes those gaps. This is the first runner of the security
assessment's Slice 2 (`security-assessment.md`); the owner asked to add
Trivy "to verify the code besides what we have".

Four scan modes, all requested:

- **fs** — filesystem vulnerability scan (reads `uv.lock`; a second opinion
  alongside pip-audit, plus anything else in the tree).
- **config** — IaC / `Containerfile` misconfiguration (our `Containerfile`,
  `Containerfile.full`, the compose files, `deploy/`).
- **secret** — accidentally committed secrets across the repo.
- **image** — OS-package CVEs in a built container image (the gap pip-audit
  cannot cover).

## Scope

- `scripts/security/scan_trivy.sh` — one entry point for the four modes plus
  an `all` convenience (fs + config + secret, the server-less ones). Uses a
  local `trivy` binary when present, else the official container image via
  `docker`/`podman` (the repo already uses both for the test DB). Trivy
  version and the severity gate are pinned and overridable by env.
- `docs/security/README.md` — add Trivy to the headless table; correct the
  stale `docs/plans/archive/security-assessment.md` path (the plan is still
  active under `docs/plans/`).
- Run the scans against our own tree/image, triage findings into
  `docs/security/assessment-2026-10-12.md`. Any confirmed High/Critical gets
  its own fix branch (+ a `KAL-SEC-*` regression test when behaviour changes).

## Not in scope

- ZAP baseline and schemathesis runners — the next Slice-2 slices, each its
  own PR.
- Wiring Trivy into CI / a nightly job — deferred to a combined
  "security runners in CI" slice so this PR stays a single-purpose tool add.
- Rendering the Helm chart for a full k8s misconfig scan — `config` mode scans
  what Trivy can parse without rendering (Containerfiles, compose, plain
  YAML); the Helm-template limitation is noted in the README.
- Fixing any finding Trivy surfaces — a finding is triaged here and fixed on
  its own branch, per the assessment's "fix or file" rule.

## Acceptance criteria

- `scripts/security/scan_trivy.sh` exists, is executable, and runs each mode
  against a local binary or the pinned container image.
- `docs/security/README.md` lists Trivy and no longer points at a
  non-existent archive path.
- The scans have been run once and their results recorded in the assessment
  file (fixed, or filed with a severity).
- `./scripts/verify.sh` passes (no `src/` change → short gate).

## Touchpoints

`scripts/security/scan_trivy.sh` (new), `docs/security/README.md`,
`docs/security/assessment-2026-10-12.md` (triage rows), `docs/plans/chores.md`
(if a follow-up falls out).

## Implementation notes

- Trivy pinned to **0.76.0** (`TRIVY_VERSION`), severity gate
  **HIGH,CRITICAL** (`TRIVY_SEVERITY`) — both env-overridable.
- No user-facing behaviour, so no `KAL-*` scenario (BDD rule 5 does not
  trigger) unless a triaged finding changes behaviour.
- **macOS bash 3.2:** a bare `"${arr[@]}"` on an empty array aborts under
  `set -u`; the container-socket args use `${arr[@]+"${arr[@]}"}` so the
  script runs under the system bash the container runner is invoked from.
- **fs/secret must skip installed envs.** A first run scanned `.venv` and the
  `.claude` agent worktrees and re-reported CVEs for NiceGUI's bundled npm
  assets and a worktree's stale `aiohttp`. `TRIVY_SKIP_DIRS` now restricts the
  walk to the source tree, so `fs` reports `uv.lock` (clean, agrees with
  pip-audit) and `secret` is clean.
- **`trivy config` has no `--no-progress` flag** (it prints no bar) — passing
  it aborted the first config run. Removed.
- **Triage of the first full run** (recorded in
  `docs/security/assessment-2026-10-12.md`):
  - `fs` clean, `secret` clean.
  - `config` → **F-6 (High)**: `Containerfile` + `Containerfile.full` run as
    root (DS-0002). Fix ships on its own branch (deployment behaviour, not this
    tooling slice). The `deploy/k3s` Helm chart is not rendered by Trivy (its
    `secretKey` default is empty by design), so a full chart scan needs
    `--helm-set`.
  - `image python:3.13-slim` → **F-7 (High, upstream)**: 44 High Debian OS
    CVEs; tracked (rebuild-on-latest mitigation), mostly no upstream fix.
