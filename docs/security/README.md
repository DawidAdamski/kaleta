# Security checks

This directory holds the output of the security assessment
(`docs/plans/archive/security-assessment.md`) and the record of how each check
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

Both are fast and need no running server; `audit_deps.sh` needs
`uv sync --group dev` first.

## Manual / dynamic checks

These need a running instance and extra tooling; they are run by hand before a
release, not on every PR. Start a local instance first:

```bash
./scripts/test_db.sh up
KALETA_SECRET_KEY=dev-only uv run kaleta   # http://localhost:8080
```

| Check | Tool | Notes |
|---|---|---|
| Web app baseline scan | OWASP ZAP baseline (`zaproxy` / `owasp/zap2docker`) | Passive scan of the running app; triage alerts into the assessment. |
| Schema-aware API fuzzing | `schemathesis run http://localhost:8080/openapi.json` | Property-based fuzzing of every `/api/v1` route against the OpenAPI doc. |
| SQL-injection probes | `sqlmap` against parameterised routes | Confirms the ORM + `schema_translate_map` leave no raw-SQL hole. |
| TLS / cookie flags | `testssl.sh` against the Caddy edge | Only meaningful against a TLS-terminating deployment, not local HTTP. |
| Login / MFA brute force | manual, or `hydra` against the login route | Confirms rate limiting and lockout. |

Kali Linux is named as the reference checklist, **not** a runtime dependency:
we install only the few tools a given pass actually uses. See the assessment
file for the full category walk, including the categories that do not apply.
