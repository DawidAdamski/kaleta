---
plan_id: aiohttp-security-bump
title: Bump aiohttp past three advisories (2 high, 1 low)
area: security (dependencies)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Bump aiohttp past three advisories (2 high, 1 low)

## Intent

GitHub Dependabot flagged three open advisories against `aiohttp 3.14.3` on
`main` — all fixed in `3.14.4`:

- **High** — aiohttp server lacks an initial request/header timeout.
- **High** — multiple instances of excessive or unbounded memory/CPU use.
- **Low** — `Secure` attribute not enforced for a shared cookie.

`aiohttp` is a transitive dependency: it reaches us through
`nicegui 3.18` (and `python-socketio`'s asyncio client). It is a runtime
dependency, so these advisories apply to a deployed instance, not just dev
tooling. The security-assessment plan's acceptance criterion requires the
dependency advisory check to pass, so this is in scope for that assessment
(its Slice 2 / the "dynamic + advisory" track).

## Scope

- Upgrade `aiohttp` in `uv.lock` only, via `uv lock --upgrade-package aiohttp`,
  to a version `>= 3.14.4` within the constraints NiceGUI already allows.
- Confirm no other package is pulled along by the bump.
- Confirm `scripts/security/audit_deps.sh` (pip-audit) reports no known
  vulnerabilities after the bump.

## Not in scope

- A broad dependency-refresh pass (that is `deps-updater`'s job, separately).
- Adding a `[tool.uv]` constraint/override — unnecessary, since NiceGUI's own
  range already admits the patched version.
- The dynamic scanner runners (ZAP / schemathesis) — those are the next Slice-2
  slice of `security-assessment.md`.

## Acceptance criteria

- `uv.lock` pins `aiohttp >= 3.14.4`; `uv tree --package aiohttp` shows it.
- `git diff uv.lock` changes only aiohttp's own block — its `version =` line
  (3.14.3 → 3.14.5) plus its `sdist`/`wheels` hash table (~176 lines in total);
  no other package's version changes and none is added or removed.
- `bash scripts/security/audit_deps.sh` → "No known vulnerabilities found".
- `./scripts/verify.sh` passes (no `src/` change → short gate, no `--e2e`).

## Touchpoints

`uv.lock` (only).

## Implementation notes

- Resolved version: **aiohttp 3.14.5** (> 3.14.4, so all three advisories are
  covered). The bump touched only aiohttp's `version` and its `wheels` hash
  table; no sibling package changed.
- No user-facing behaviour changes, so no `KAL-*` scenario applies (BDD rule 5
  does not trigger). The standing regression guard for this class of issue is
  `scripts/security/audit_deps.sh` (pip-audit, from the assessment's Slice 1),
  which now reports clean; wiring it into CI/nightly is tracked under
  `security-assessment.md` Slice 2.
