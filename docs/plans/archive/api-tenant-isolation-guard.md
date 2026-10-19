---
plan_id: api-tenant-isolation-guard
title: API cross-family isolation — a guard so no new route can skip tenant binding
area: security (api)
effort: small
status: archived
archived_at: 2026-10-19
roadmap_ref: ../../roadmap.md
---

# API cross-family isolation — a guard so no new route can skip tenant binding

## Intent
Follow-up to `security-assessment` finding **F-5** ("tenant schema isolation is
the *single* control for cross-family reads — no defense-in-depth per-row
predicate", `docs/security/assessment-2026-10-12.md`). A source review of the
request path confirmed the control is sound today: every `/api/v1` data route
opens its session through `get_session`, which runs `resolve_request_tenant` and
binds the request to one family's schema via `schema_translate_map`; the only
public route is `health` (registry-only). There are no `tenant_id` columns to
fall back on (ADR-35/38).

Because it is a *single* control, the real risk is a **future** route that opens
a session some other way — the public registry session, or a raw session factory
— and so reads across families. This slice adds a cheap, deterministic guard that
makes that mistake fail the test suite the moment it is written, turning "the one
control" into "the one control, enforced".

## Scope
- **`tests/integration/test_api_tenant_isolation_guard.py`** (new): a static
  guard that reads the `src/kaleta/api/v1` source (AST + text, no running app,
  so it can't drift with a FastAPI internals change) and asserts, per module
  except the exempt `health`/`__init__`:
  1. every `@router.<method>` handler takes `session=Depends(get_session)` (the
     tenant-bound session);
  2. that `get_session` is imported from **`kaleta.api.deps`** — not the plain
     `kaleta.db.session.get_session`, which does not run
     `resolve_request_tenant` (the closest real bypass, caught after review);
  3. no v1 data module references `get_public_session`, `AsyncSessionFactory`,
     `make_session_factory`, or `async_session` (a tripwire for the common ways
     to open a session that skip the family binding — not an exhaustive sieve).
- **`docs/security/assessment-2026-10-12.md`**: a short note under F-5 that the
  guard now enforces the invariant, so F-5 stays "accepted by design" *and*
  defended.

**Not in scope (binding):**
- No change to any route, dependency, or the isolation mechanism itself — the
  mechanism is already correct; this only pins it.
- Not the F-1..F-4 finding fixes (their own slice) nor the dynamic scanners
  (`security-assessment` Slice 2).
- No per-row `tenant_id` predicate — ADR-35/38 keeps isolation at the schema
  level; this guard defends that choice rather than replacing it.
- No new `KAL-*` scenario: this is an internal architectural invariant, not
  user-facing behaviour (consistent with other guard tests, e.g. the dimension
  dispatchers' `assert_never`).

## Acceptance criteria
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`
- `./scripts/verify.sh`

Fail-on-old / fail-on-mistake: the guard is the deliverable, so "fail on old"
is "fail on the mistake it guards against". Verified by hand — pointing a v1
handler at `get_public_session` (or dropping its `get_session` dependency) makes
the guard fail; reverting restores green. Today's tree passes (13 data modules,
all through `get_session`; only `health` public).

## Touchpoints
- `tests/integration/test_api_tenant_isolation_guard.py`
- `docs/security/assessment-2026-10-12.md`

## Open questions
- None blocking.

## Implementation notes
- **Static, not runtime.** FastAPI 0.143's `_IncludedRouter` keeps included
  routers lazily nested rather than flattening `app.routes`, so walking the
  route table for dependants is version-fragile. An AST read of the source is
  simpler, deterministic, and survives FastAPI upgrades — and it reads the
  invariant the way a human would state it ("every handler takes
  `Depends(get_session)`").
- **Why the three checks.** The dependency check (1) catches a route wired to
  the wrong session dependency; the import-origin check (2) catches a handler
  that depends on a *different* `get_session` (e.g. `kaleta.db.session`'s, which
  skips `resolve_request_tenant`); the text tripwire (3) catches a handler that
  bypasses dependencies entirely and opens a session from a factory. Checks 1–2
  are the primary guarantees; 3 is a loud tripwire for the common names, not an
  exhaustive sieve (an aliased import or a direct `AsyncSession(engine)` would
  slip past — acceptable for defense-in-depth). Together they cover the
  realistic ways "a new route reads another family's rows".
- **`health` is the one exemption** — registry-only (`get_public_session`), no
  tenant data, mounted outside the auth-gated `v1_router`. If a second public
  route is ever added, the guard's exempt set is where that decision is recorded.
</content>

## Implementation

Landed on 2026-10-19 (PR #297).

| SHA | Author | Date | Message |
|---|---|---|---|
| `9485f68` | Dawid Adamski | 2026-10-19 | Merge pull request #297 from DawidAdamski/feat/api-tenant-isolation-guard |

**Files changed:**
- docs/plans/api-tenant-isolation-guard.md
- docs/security/assessment-2026-10-12.md
- tests/integration/test_api_tenant_isolation_guard.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
