# Security checks

This directory holds the output of the security assessment
(`docs/plans/security-assessment.md`) and the record of how each check
is run. The assessment treats Kali Linux's tool categories as a *checklist of
attack surfaces* and maps each to a concrete check against **our own** instance
— never against anyone else's systems.

- **The findings** live in `assessment-<date>.md` (one file per pass).
- **The headless checks** live in `../../scripts/security/` and run against a
  local or staging instance we control.

## Headless checks (runnable, CI-safe)

| Check | Command | What it covers |
|---|---|---|
| Dependency advisories | `./scripts/security/audit_deps.sh` | No pinned third-party dependency has a known CVE (pip-audit / OSV). |
| Static security lint | `uv run ruff check src/ --select S` | Bandit-derived checks (`S` family), already part of `verify.sh`. |
| Filesystem / IaC / secret scan | `./scripts/security/scan_trivy.sh {fs,config,secret,all}` | Trivy: `fs` reads `uv.lock` (a second opinion to pip-audit); `config` scans `Containerfile*`, the compose files and `deploy/` for misconfig; `secret` scans for committed secrets. `all` runs the three server-less modes. |
| Container image CVEs | `./scripts/security/scan_trivy.sh image <ref>` | Trivy: OS-package CVEs in a built image — the layer pip-audit cannot see. Build the image first (`podman build -t kaleta:local -f Containerfile .`) or pass a registry ref. |

`audit_deps.sh` needs `uv sync --group dev` first. `scan_trivy.sh` uses a
local `trivy` binary when present, otherwise the official container image via
`docker`/`podman` (pinned `TRIVY_VERSION`, gate `TRIVY_SEVERITY`,
default `HIGH,CRITICAL`). Its `config` mode scans only what Trivy parses
without rendering — the `deploy/k3s` Helm *templates* are skipped (they are not
valid YAML until rendered); the plain compose files and `Containerfile*` are
covered.

The two server-less checks also run **nightly in CI**
(`.github/workflows/security-nightly.yml`, scheduled + `workflow_dispatch`):
`audit_deps.sh` and `scan_trivy.sh all`. The workflow only invokes the scripts —
they stay the single source of truth — so a new advisory, misconfiguration or
committed secret is caught without waiting for a manual run, and without adding
to PR latency. The dynamic runners below are not wired nightly (they need a
running instance).

## Dynamic runners (scripted, need a live instance)

These are scripted like the headless checks but scan a **running** instance, so
they are run against a local or staging target rather than in the PR gate. Start
an instance first:

```bash
./scripts/test_db.sh up
KALETA_SECRET_KEY=dev-only uv run kaleta   # http://localhost:8080
```

| Check | Command | What it covers |
|---|---|---|
| Web app baseline scan | `./scripts/security/scan_zap.sh [target-url]` | OWASP ZAP **baseline** (passive): spiders the running app and runs ZAP's passive rules — security response headers, cookie flags, info disclosure. No attack payloads. Exits non-zero on a FAIL (set `ZAP_FAIL_ON=WARN` to also fail on warnings). Triage alerts into the assessment. |
| Schema-aware API fuzzing | `./scripts/security/scan_schemathesis.sh [target-url]` | **schemathesis**: property-based fuzzing of every documented `/api/v1` operation against `/api-docs/openapi.json` (API docs must be on — debug or `KALETA_API_DOCS=true`). Default check `not_a_server_error` (no fuzzed input should 5xx). For a deeper authenticated conformance fuzz: `ST_BEARER=<token> ST_CHECKS=all ...` against a seeded instance. |

`scan_zap.sh` always uses the ZAP container image (there is no common local
binary) via `docker`/`podman` (pinned `ZAP_VERSION`, default gate `FAIL`). A
target whose host is `localhost`/`127.0.0.1` is reached from inside the
container through `host.docker.internal` — this needs Docker 20.10+/Desktop or
Podman 4.1+, and the app must listen on `0.0.0.0` (the default `KALETA_HOST`),
since on Linux Docker the gateway is the bridge IP and an app bound only to
`127.0.0.1` would be unreachable. Set `ZAP_REPORT_DIR` (an absolute path) to
also write `report.html` + `report.json`.

## Manual checks

These need a running instance and extra tooling run by hand before a release,
not on every PR (start a local instance as above):

| Check | Tool | Notes |
|---|---|---|
| SQL-injection probes | `sqlmap` against parameterised routes | Confirms the ORM + `schema_translate_map` leave no raw-SQL hole. |
| TLS / cookie flags | `testssl.sh` against the Caddy edge | Only meaningful against a TLS-terminating deployment, not local HTTP. |
| Login / MFA brute force | manual, or `hydra` against the login route | Confirms rate limiting and lockout. |

Kali Linux is named as the reference checklist, **not** a runtime dependency:
we install only the few tools a given pass actually uses. See the assessment
file for the full category walk, including the categories that do not apply.
