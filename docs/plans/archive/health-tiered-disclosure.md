---
plan_id: health-tiered-disclosure
title: /health — tiered disclosure so a family can never read another family's operational state
area: security (api)
effort: small
status: archived
archived_at: 2026-10-19
roadmap_ref: ../../roadmap.md
---

# /health — tiered disclosure so a family can never read another family's operational state

## Intent
Security assessment finding **F-1** (`docs/security/assessment-2026-10-12.md`):
the unauthenticated `GET /health` returns app version, migration state, the
sign-in backend, a cross-family keyring-session count, the count of families
behind head, **and the ids of suspended families**. The suspended-family ids
(and the cross-family counts) are exactly the cross-family recon that must not
leak once the instance hosts more than one family.

This slice gives `/health` **three disclosure tiers**, keyed to *who is asking*:

| Tier | Credential | Body |
|---|---|---|
| **public** | none | `status`, `database_ok` (+ 503 when DB down) |
| **family** | a valid family bearer token, **or** a signed-in cookie session | public + `version`, `auth_backend`, `migrations_pending` (bool) |
| **admin** | the `KALETA_API_TOKEN` env token, **or** a cookie session the registry confirms is an instance administrator | family + `tenants_pending_migration` (count), `keyring_sessions`, `suspended_tenants` |

The product principle the owner set: *administrative health is a different thing
from a family admin's health*. A **family-scoped credential (a family bearer
token) never reaches the admin tier**, even if its owner happens to be the
instance administrator — the administrative view requires an instance-level
credential. So no family's credential can ever reveal another family's ids or
the instance's cross-family counts.

## Scope
- **`src/kaleta/schemas/health.py`**: make the tiered fields optional
  (`version`, `auth_backend`, `migrations_pending`, `tenants_pending_migration`,
  `keyring_sessions`, `suspended_tenants` all `… | None = None`); `status` and
  `database_ok` stay required. The route serialises with
  `response_model_exclude_none=True`, so a lower tier yields a trimmed body.
- **`src/kaleta/services/health_service.py`**: `check(*, include_family: bool,
  include_admin: bool)` computes only what the tier needs — the public probe
  does **no** registry reads (no suspended-tenant query, no revision compare);
  the family tier adds the version / backend / `migrations_pending` bool; the
  admin tier adds the pending **count**, the keyring count and the suspended
  ids. `HealthSnapshot` fields become optional to match.
- **`src/kaleta/api/v1/health.py`**: a `health_audience(...)` resolver
  (`Literal["public","family","admin"]`) used by both the `/api/v1/health`
  route and the `/health` alias. It never raises — a probe must not 401 — so a
  bad or unknown credential is simply treated as `public`.
- **`docs/bdd.md`**: trim **KAL-API-004** to the public liveness contract; add
  **KAL-SEC-001** for the tiered disclosure (the F-1 regression); reword
  **KAL-TEN-010** / **KAL-TEN-013** / **KAL-OPS-001** to read the *administrative*
  (or authenticated) probe where they rely on tier-gated fields.
- **`docs/security/assessment-2026-10-12.md`**: flip F-1 from *Tracked* to
  *Fixed*, with the tier table and the KAL-SEC-001 reference.
- Tests: `tests/integration/test_health.py` + `tests/unit/api/test_health.py`
  updated to the tiered contract; a new integration test proving a **family
  bearer token cannot see `suspended_tenants`** (fail-on-old: it is returned
  unauthenticated today).

### Audience resolution (binding)
- **Bearer**: `is_env_token(tok)` → **admin** (the env token is, by construction,
  the oldest enabled instance administrator, `env_token_membership`). Otherwise
  parse the tenant id from the `kt_<tenant>_<secret>` prefix, require the tenant
  `ACTIVE`, bind its schema and `authenticate_bearer` the token → **family** when
  it authenticates a member, else **public**. A family token never yields admin.
- **Cookie** (health is `GET`, a safe method): `authenticated_user_id(request)`
  binds + validates the session; `None` → **public**. Otherwise **family**, and
  `is_instance_admin(public, subject=…, email=…, auth_backend=…,
  admin_emails=settings.instance_admin_emails)` against the registry (never the
  `SESSION_INSTANCE_ADMIN` nav hint) promotes to **admin**.

**Not in scope (binding):**
- No change to who may *sign in*, mint tokens, or open `/admin`.
- No new per-family health payload (a genuine "this family's own health" view is
  a possible later slice; here the family tier only withholds cross-family data,
  it does not add family-scoped data).
- F-2..F-4 are their own slices.

## Acceptance criteria
- `uv run pytest tests/integration/test_health.py tests/unit/api/test_health.py -q`
- `./scripts/verify.sh` (no `src/kaleta/views/` change → short gate)
- Fail-on-old: the new family-token test asserts `suspended_tenants` absent;
  on the pre-change route (unauthenticated body carries it, and a bearer saw
  everything) it is present → test fails. Verified by a backup swap.

## Touchpoints
- `src/kaleta/schemas/health.py`
- `src/kaleta/services/health_service.py`
- `src/kaleta/api/v1/health.py`
- `tests/integration/test_health.py`
- `tests/unit/api/test_health.py`
- `tests/integration/test_hosted_operations.py` (call site: `check()` now takes the tier flags)
- `docs/bdd.md`
- `docs/security/assessment-2026-10-12.md`
- `docs/plans/chores.md` (the security chore note)

## Open questions
- None blocking. Owner chose "detail behind a credential" and drew the
  administrative-vs-family line; the resolution rules above encode it.

## Implementation notes
- **Why a family bearer token never reaches admin.** Determining admin-ness from
  a family token would need a new registry lookup `(tenant_id, user_id) →
  auth_subject/email` (there is no helper for it today; a bearer token natively
  yields only tenant + `user_id`). Beyond the cost, a family-scoped credential
  granting a cross-family administrative view is the wrong shape. The admin tier
  is therefore reached only by an instance-level credential: the env token, or a
  cookie session re-checked against the registry. Recorded as a deliberate limit.
- **The probe never 401s, and never 500s.** Monitors hit `/health` and expect
  200/503, never 401 or 500; `health_audience` swallows a bad credential — and
  any resolution failure (a database that is down while a credential is present,
  an unconfigured factory) — to `public`, logging it. The route then maps an
  unreachable database to 503 as before. A unit test drives a resolver that
  raises and asserts `public`.
- **A family bearer token authenticates, which writes.** The family tier calls
  `ApiTokenService.authenticate_bearer`, which updates `last_used_at` and
  commits. So an *authenticated* liveness probe touches the DB — a repeatedly
  polling authenticated monitor bumps `last_used_at`. Accepted: it is the
  existing token-authentication behaviour and the cost is one small write per
  authenticated probe; an unauthenticated monitor (the common case) writes
  nothing.
- **`check()` is fail-closed.** Its `include_family` / `include_admin` flags are
  required keyword arguments (no fail-open default), so a future caller cannot
  accidentally get full disclosure by calling `check()` with no tier.
- **Integration-harness limit on the *family* tier.** The integration fixtures
  mint their *family* bearer token on a rolled-back connection that the probe's
  own `AsyncSessionFactory` (opened inside `health_audience`, as in production)
  cannot see, so an end-to-end real *family-token* integration call always
  resolves to `public`. The family tier is therefore pinned at the unit level:
  `test_family_bearer_through_the_real_resolver_hides_cross_family_state` wires
  the real `health_audience` to the route and fakes only the DB seams; the
  route-tier tests override the audience; the cookie tests monkeypatch the
  registry check. The **admin** tier, by contrast, *is* reached end-to-end in
  integration: `is_env_token` resolves the `KALETA_API_TOKEN` env token with no
  database read, so `test_env_token_health_reports_a_git_derived_version`
  (integration) drives the real resolver to the admin tier over a live ASGI
  call — it covers KAL-OPS-001 (version agreement) and asserts the cross-family
  `suspended_tenants` is present there. The integration public-tier test keeps
  the fail-on-old contract.
- **Fail-on-old verified.** Forcing full disclosure in `_health_payload`
  (`include_family=True, include_admin=True` regardless of audience, a backup
  swap) makes all three public-tier tests fail on `suspended_tenants` leaking;
  reverting restores green.
</content>
</invoke>

## Implementation

Landed on 2026-10-19 (PR #299).

| SHA | Author | Date | Message |
|---|---|---|---|
| `68b6378` | Dawid Adamski | 2026-10-19 | Merge pull request #299 from DawidAdamski/feat/health-tiered-disclosure |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/health-tiered-disclosure.md
- docs/security/assessment-2026-10-12.md
- src/kaleta/api/v1/health.py
- src/kaleta/schemas/health.py
- src/kaleta/services/health_service.py
- tests/integration/test_health.py
- tests/integration/test_hosted_operations.py
- tests/unit/api/test_health.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
