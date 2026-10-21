---
plan_id: security-zap-baseline
title: ZAP baseline runner for the security assessment (Slice 2a)
area: security (dynamic scanners)
effort: small
status: archived
archived_at: 2026-10-21
roadmap_ref: ../../roadmap.md
---

# ZAP baseline runner for the security assessment (Slice 2a)

## Intent

`docs/plans/security-assessment.md` Slice 2 wires the dynamic scanners that need
a live instance. This slice delivers the first one: an **OWASP ZAP baseline**
runner. The baseline is a passive spider + passive scan — it sends no attack
payloads, so it is safe to point at our own running instance. It catches the
unauthenticated-surface hygiene a static pass cannot: missing/weak security
headers (CSP, X-Frame-Options/frame-ancestors, X-Content-Type-Options,
Permissions-Policy), cookie flags over HTTP, information disclosure in responses.

Tooling-only slice, mirroring the Trivy runner (`security-trivy-scan`, PR #308):
the script + docs, plus a triage of the first run into the assessment. Any
confirmed finding is fixed on its own later branch with a `KAL-SEC-*` regression
test — not here.

## Scope

- **`scripts/security/scan_zap.sh`** (new, executable) — run the ZAP baseline
  against a target URL (default `http://localhost:8080`). Same shape as
  `scan_trivy.sh`: pinned image version + gate via env overrides, a container
  runner picked from `docker`/`podman` (ZAP ships as a container; there is no
  common local binary). Host-networking handled so a container can reach an app
  on the host's `localhost`. Exit non-zero when the baseline reports a FAIL at
  or above the configured threshold.
- **`docs/security/README.md`** — move ZAP from the "manual/dynamic" table to a
  new "dynamic runners (scripted)" row with the concrete command; keep the
  manual note for tools still run by hand (sqlmap, testssl, hydra).
- **`docs/security/assessment-2026-10-12.md`** — triage the first run: either
  "ZAP baseline clean" or new `F-*` rows (severity + the ZAP alert id). Update
  the Web-application-analysis category line and the `Next` section.
- **`docs/plans/security-assessment.md`** — Slice-2 progress note: ZAP runner
  landed; schemathesis + nightly CI still open.

## Not in scope

- An **authenticated** ZAP scan (context file + session token). The baseline
  covers the unauthenticated surface; an authenticated active scan is a heavier,
  later step.
- The **active** scan / full scan (sends payloads) — baseline (passive) only.
- `schemathesis` (Slice 2b, its own PR) and wiring the headless checks into
  nightly CI (the follow-up after both runners land).
- Fixing any finding the run surfaces — each gets its own branch + `KAL-SEC-*`.

## Acceptance criteria

- `./scripts/security/scan_zap.sh` runs the ZAP baseline against a live local
  instance through `docker` or `podman`, reaching the host app, and exits
  non-zero on a FAIL at/above the threshold (verified by a real run).
- The runner is `scripts/security/` executable (mode 100755) and self-documents
  its usage + env overrides in a header, matching `scan_trivy.sh`.
- `docs/security/README.md` lists the scripted ZAP command; the assessment
  records the first run's result (clean, or `F-*` rows with ZAP alert ids).
- `./scripts/verify.sh` passes (no `src/` change → short gate).

## Touchpoints

`scripts/security/scan_zap.sh` (new), `docs/security/README.md`,
`docs/security/assessment-2026-10-12.md`, `docs/plans/security-assessment.md`,
`docs/plans/chores.md` (F-8 fix inbox line).

## Implementation notes

- **Runner shape.** `scan_zap.sh` mirrors `scan_trivy.sh`: pinned image tag
  (`ZAP_VERSION`, default `2.16.1`, `ghcr.io/zaproxy/zaproxy`), env-overridable
  gate/runner, `docker`|`podman` picked automatically (no local ZAP binary
  exists). The baseline command is `zap-baseline.py -t <url> -m <mins>`.
- **No `-t`.** An early version allocated a TTY (`run --rm -t`). Under `nohup`
  or a CI runner there is no terminal; the TTY detaches the container and the
  wrapper returns early with a truncated log while the scan runs on. Dropped it
  — a headless runner must not allocate a TTY.
- **Host networking.** The app runs on the host, so a `localhost`/`127.0.0.1`
  target is rewritten to `host.docker.internal` with
  `--add-host host.docker.internal:host-gateway` (portable across Docker
  20.10+/Desktop and recent Podman). A non-local target passes through.
- **Gate.** `ZAP_FAIL_ON=FAIL` (default) passes `-I` so warnings print but do
  not fail the gate — the ZAP baseline reports missing-header hardening as WARN,
  which is triage material, not a hard CI failure yet. `ZAP_FAIL_ON=WARN` drops
  `-I`. Exit-code mapping of `zap-baseline.py`: `0` nothing at/above the gate
  (with `-I`, warnings count as PASS, so warnings-only still exits 0); `1` a
  FAIL; `2` warnings-only, which is reachable **only** without `-I` (the WARN
  gate) and is a failure there; `3+` a run error, surfaced verbatim. So under
  the default FAIL gate the script sees only 0, 1 or a run error.
- **Reports optional.** By default only stdout (the PASS/WARN/FAIL summary) is
  produced — no bind mount, so no uid-1000-writability problem. `ZAP_REPORT_DIR`
  mounts a dir (made world-writable for the ZAP user) and writes
  `report.html` + `report.json`.
- **First run (triaged into `assessment-2026-10-12.md`).** 0 FAIL, 11 WARN, 56
  PASS against `http://localhost:8080`. One real class → **F-8 (Medium)**: no
  security response headers (CSP 10038, anti-clickjacking 10020,
  X-Content-Type-Options 10021, Permissions-Policy 10063, COOP/COEP/CORP 90004).
  Rest is scanner noise (ZAP-out-of-date, Modern-Web-App, suspicious-comments,
  non-storable-content; "Dangerous JS Functions" against the bundled front-end).
  Passes confirmed the F-1/F-3 work holds over HTTP (cookie flags, no
  version/server leak, no debug disclosure, no sensitive data in URLs). F-8 is
  **filed, not fixed here** — it gets its own branch + `KAL-SEC-*`.
- **Both gate paths validated by real runs.** Default `FAIL` gate against the
  live instance → exit **0** (11 WARN, 0 FAIL — warnings ignored under `-I`).
  `ZAP_FAIL_ON=WARN` against the same instance → exit **1** ("warnings present
  … gate failed"), exercising the non-zero path the first acceptance criterion
  asks for. The empty-array `add_host` expansion was checked under
  `set -euo pipefail` on the host's bash 3.2.57 (no "unbound variable" abort).
- **Tooling-only slice.** Like `security-trivy-scan`, no new `KAL-SEC-*`
  scenario: a scanner script is not user-facing app behaviour. verify.sh runs
  the short gate (no `src/` change).

## Implementation

Landed on 2026-10-21.

| SHA | Author | Date | Message |
|---|---|---|---|
| `37b3d00` | Dawid (Ani) | 2026-10-20 | feat(security): add an OWASP ZAP baseline runner (Slice 2a) |

**Files changed:**
- docs/plans/chores.md
- docs/plans/security-assessment.md
- docs/plans/security-zap-baseline.md
- docs/security/assessment-2026-10-12.md
- docs/security/README.md
- scripts/security/scan_zap.sh

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.

**Archival note:** archived with `plan_archive.sh --fast` (acceptance criteria not re-run). PR #311 already merged with CI green. Operator-tool criteria (`scan_trivy.sh`, `scan_zap.sh`) need docker and/or a live instance and are not re-runnable CI gates; `plan_archive.sh` also mis-parses prose bullets whose first backticked token is a file path. Those criteria were verified by real runs at implementation time, recorded in `docs/security/assessment-2026-10-12.md` and this plan's Implementation notes. Feature commit: 37b3d00 (PR #311).
