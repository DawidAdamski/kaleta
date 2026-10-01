---
plan_id: hosted-tenancy-foundation
title: Hosted — auth provider, tenant registry and schema per account
area: auth / db / setup
effort: large
status: archived
archived_at: 2026-10-01
roadmap_ref: ../../roadmap.md#2027-directions
---

# Hosted — auth provider, tenant registry and schema per account

## Intent

The hosted Kaleta must serve many accounts from one Supabase project
while the operator knows only each account's user id and e-mail, and the
self-hosted Podman/SQLite install must keep working exactly as it does.
This plan lays the multi-tenant foundation decided in
[ADR-35](../../adr/035-hosted-multi-tenancy-and-user-held-encryption.md):
identity through Supabase Auth behind an `AuthProvider` interface, a
`public.tenants` registry, one Postgres schema per account selected per
request, and provisioning at sign-up. Encryption is the next plan
([`hosted-field-encryption`](../hosted-field-encryption.md)); this plan
leaves the hooks it needs.

## Scope

### 1. Runtime modes

- `KALETA_TENANCY=single|multi` (default `single`). `single` is today's
  behaviour: one database, one user, no schema translation.
- `KALETA_AUTH_BACKEND=local|supabase` (default `local`). `multi`
  requires `supabase`; the settings validator refuses other
  combinations with a clear message.
- New settings, all `KALETA_`-prefixed: `SUPABASE_URL`,
  `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (server-side only,
  used for admin calls such as deleting an auth user), `PUBLIC_URL`
  (for e-mail redirect links).

### 2. `AuthProvider` interface (`kaleta/auth/providers/`)

- `Protocol` with `sign_up(email, password) -> SignUpResult`,
  `sign_in(email, password) -> Identity | MfaRequired`,
  `sign_out(session)`, `request_password_reset(email)`,
  `confirm_password_reset(token, new_password)`, `delete_identity(subject)`.
  `Identity` carries `subject` (opaque string), `email`, `email_verified`.
- `LocalAuthProvider` wraps the existing `AuthService` (username stays
  the login name; `subject` is `str(user.id)`). No behaviour change for
  self-hosted installs; `views/login.py` and `views/create_account.py`
  are re-pointed at the provider, not rewritten.
- `SupabaseAuthProvider` talks to GoTrue over HTTPS with `httpx`
  (`/auth/v1/signup`, `/token?grant_type=password`, `/recover`,
  `/user`, `/logout`). Verifies the returned access token's `sub` and
  `email` claims. No `supabase-py` dependency — the surface used is
  five endpoints. `httpx` goes into a new `hosted` extra together with
  `asyncpg`/`psycopg2` (fold the existing `postgres` extra into it or
  keep both; decide in implementation notes).
- Session (`kaleta/auth/session.py`) gains `SESSION_TENANT_ID`,
  `SESSION_AUTH_SUBJECT`, `SESSION_EMAIL`. `login_session` takes an
  `Identity` plus the resolved tenant. Nothing secret goes into
  `app.storage.user` — it is persisted to disk by NiceGUI.
- Login page in `supabase` mode: e-mail + password, "forgot password"
  link, sign-up link, "check your inbox" state after sign-up. Local
  mode keeps the username form. i18n keys under `auth.*`.

### 3. Tenant registry (`public.tenants`, `public.tenant_members`)

- New models in `kaleta/models/tenant.py`, mapped with
  `__table_args__ = {"schema": "public"}` and **excluded from the
  per-tenant metadata** (see §4):
  - `Tenant`: `id` (int PK), `schema_name` (unique), `name` (nullable,
    encrypted later), `status` (`provisioning|active|suspended|
    rekeying|deleting`), `key_version` (int, 1), `created_at`,
    `last_seen_at`.
  - `TenantMember`: `id`, `tenant_id` (FK), `auth_subject` (unique —
    one identity belongs to one tenant), `email` (unique, lowercase),
    `role` (`owner|member`), `status` (`pending|active|removed`),
    `user_id` (the member's row in the tenant-schema `users` table),
    `joined_at`, `removed_at`, plus the nullable key-material columns
    the encryption plan fills (`public_key`, `private_key_wrapped`,
    `private_key_salt`, `kdf_params`, `recovery_wrapped`,
    `recovery_salt`, `dek_sealed`). Adding them now avoids a second
    registry migration.
  - `TenantInvite` (`token_hash`, `tenant_id`, `email`, `role`,
    `expires_at`, `accepted_at`) — used by
    [`hosted-household-sharing`](../hosted-household-sharing.md); created
    here so the registry migration is one file.
  This plan creates every tenant with exactly one `owner` member; the
  household plan adds the second to fourth.
- Registry migrations live in a second Alembic environment
  (`alembic_public/`, `version_table="alembic_version_public"`), run
  once per Supabase project. Tenant-schema migrations keep using
  `alembic/`.
- `TenantService` (public-schema session): `get_member_by_subject`
  (→ member + tenant), `provision(identity) -> Tenant` (tenant + owner
  member), `mark_seen`, `suspend`, `delete`.
- In `single` mode the registry does not exist; `TenantContext` is a
  fixed sentinel (`schema=None`) and `AsyncSessionFactory` behaves as
  today.

### 4. Schema per account

- Tenant schemas are named `t_` + 12 hex chars from `secrets.token_hex`
  — never derived from the e-mail.
- `kaleta/db/tenant_context.py`: a `ContextVar[TenantContext]` set by a
  middleware (`kaleta/auth/middleware.py` already guards routes) from
  the session on every request and NiceGUI page, and by `api/deps.py`
  from the bearer token's owning tenant. `TenantContext` holds
  `tenant_id`, `schema`, and a slot for the encryption `KeyRing` entry
  the next plan adds.
- `_SessionProxy.__call__` reads the context and returns a session bound
  to `engine.execution_options(schema_translate_map={None: schema})`.
  One engine, one pool; no `SET search_path`. Model `__table__` objects
  stay schema-less so SQLite keeps working.
- Provisioning at first sign-in of a verified identity:
  `CREATE SCHEMA t_xxx`, then `upgrade_to_head` from
  `services/setup_service.py` extended with a `schema` argument that
  Alembic receives through `-x tenant_schema=` and applies via
  `version_table_schema` and `schema_translate_map` in `alembic/env.py`;
  then insert the owner's `users` row (`users` gains `email` and
  `display_name`; `username` = e-mail; no local password —
  `password_hash` becomes nullable in a tenant migration and
  `LocalAuthProvider` refuses a NULL hash). One `users` row per member
  from here on: the household plan inserts the others at approval.
  `TenantContext` carries `member_user_id`, and services that create
  rows on `UserOwnedMixin` tables set `user_id` from it (attribution,
  not access control). Provisioning is idempotent
  and runs under an advisory lock keyed on the subject so a double
  submit does not create two schemas.
- Startup in `multi` mode: migrate `public`, then iterate `tenants`
  and bring every schema to head (`scripts/migrate_tenants.py`, also
  usable as a one-off job). The health endpoint reports
  `tenants_pending_migration`.
- `KALETA_MODE=api` with bearer tokens: `ApiToken` lives in the tenant
  schema, so token lookup must know the tenant. Tokens get a
  tenant-id prefix (`kt_<tenant>_<secret>`) so `api/deps.py` can pick
  the schema before hashing and looking the token up.
- Backups, `BackupScheduler`, `IntegrityService` and the SQLite
  housekeeping page are `single`-mode only; in `multi` mode they are
  not started and Settings → Data hides the SQLite cards (Supabase's
  own backups cover the database; per-account export stays available).

### 5. Podman parity

- `docker-compose.yml` unchanged in behaviour (SQLite, `single`,
  `local`). Add a commented `kaleta-hosted` service showing the `multi`
  + `supabase` env block against an external Postgres for local
  end-to-end testing (Supabase CLI local stack or plain `postgres:16`).
- CI: the existing `postgres` job runs the suite in `single` mode as
  today; add a `multi` matrix entry that provisions two tenants and
  runs the tenant-isolation tests (§6). Local auth is used in that job
  through a `FakeAuthProvider` fixture — CI does not talk to Supabase.

### 6. Tests

- Unit: `TenantService.provision` idempotency; `schema_translate_map`
  applied from context; settings validator rejects `multi` + `local`;
  `SupabaseAuthProvider` against recorded GoTrue responses (`respx` or
  `httpx.MockTransport`).
- Integration (Postgres only): two tenants, same account name in each,
  each sees only its own rows through every `api/v1` router; a request
  with no tenant context fails closed (`500`, never the other tenant's
  data); API token of tenant A rejected on tenant B.
- e2e: sign-up → verification stub → first login provisions → dashboard
  loads (local `FakeAuthProvider` with auto-verified e-mail).

### Not in scope

- Encryption, passphrase, recovery codes → `hosted-field-encryption`.
- Deployment, Redis session storage, demo reset, billing flags →
  `hosted-supabase-rollout`.
- MFA → `auth-two-factor`.
- Inviting, approving and removing members, re-keying →
  [`hosted-household-sharing`](../hosted-household-sharing.md). This plan
  only lays down the tables and the one-row-per-member rule.
- Migrating an existing single-tenant SQLite database into a hosted
  account (a later "import my self-hosted data" plan; the full-schema
  backup roundtrip from `backup-full-schema-roundtrip` is the seed).

## Acceptance criteria

- `uv run pytest tests/unit/auth tests/unit/services/test_tenant_service.py -q`
- `uv run pytest tests/integration/test_tenant_isolation.py -q` (Postgres job)
- `! KALETA_TENANCY=multi KALETA_AUTH_BACKEND=local uv run python -c "import kaleta.config"` (the import must exit non-zero)
- `uv run pytest tests/e2e/test_auth.py -q` (existing single-mode flows unchanged)
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `grep -c "KAL-TEN-" docs/bdd.md | grep -qE '^[1-9]'` — new area `KAL-TEN-*`: sign-up provisions a schema; tenant isolation; failed-closed context; API token scoped to tenant
- `[manual]` Against a Supabase project: sign up with a real e-mail, click the verification link, log in, see an empty dashboard; `public.tenants` has one row and `information_schema.schemata` one `t_` schema.

## Touchpoints

`src/kaleta/config/settings.py`, `src/kaleta/auth/providers/{__init__,base,local,supabase}.py`
(new), `src/kaleta/auth/session.py`, `src/kaleta/auth/middleware.py`,
`src/kaleta/api/deps.py`, `src/kaleta/db/session.py`,
`src/kaleta/db/tenant_context.py` (new), `src/kaleta/models/tenant.py`
(new), `src/kaleta/models/user.py` (nullable `password_hash`),
`src/kaleta/services/tenant_service.py` (new),
`src/kaleta/services/setup_service.py`, `src/kaleta/services/api_token_service.py`,
`src/kaleta/main.py` (mode gating of schedulers), `alembic/env.py`,
`alembic_public/` (new), `scripts/migrate_tenants.py` (new),
`src/kaleta/views/login.py`, `src/kaleta/views/create_account.py`,
`src/kaleta/views/settings/data_tab.py`, `src/kaleta/i18n/{en,pl}.json`,
`pyproject.toml` (`hosted` extra, import-linter: `kaleta.auth.providers`
sits with `kaleta.auth`), `docker-compose.yml`, `.github/workflows/ci.yml`,
`docs/tech-stack.md`, `docs/deployment.md`, `docs/bdd.md`.

## Open questions

- The `users` table stays inside each tenant schema (one row per
  member, mirroring `tenant_members`) because every existing FK points
  at it and SQLite parity needs it. Keeping the two in sync is a
  `TenantService` concern: e-mail changes in Supabase update both;
  `display_name` lives only in the tenant `users` row and is the
  member's to edit.
- Should a tenant be provisioned at sign-up (before verification) or
  at first verified login? First verified login avoids orphan schemas
  from bots; the trade-off is a few seconds' wait on first login.
- `httpx` versus `aiohttp`: NiceGUI already pulls `httpx`; confirm and
  avoid a second HTTP client.

## Implementation notes

### Open questions — resolved

- **`users` stays per tenant** (as the plan states). `TenantService` keeps
  `tenant_members.email` and the tenant `users.email`/`username` in step:
  `membership_for_sign_in` compares the provider's e-mail with the registry at
  every sign-in and updates both. `display_name` starts as the e-mail's local
  part and lives only in the tenant row.
- **Provisioned at first verified sign-in**, not at sign-up (the plan's §4
  default). Sign-up only creates the identity at Supabase and shows "check
  your inbox"; `TenantService.provision` refuses an unverified identity.
- **httpx, not aiohttp.** NiceGUI already depends on httpx; it is also named
  in the `hosted` extra so the hosted install states what it calls.
- **`hosted` vs `postgres` extras:** both kept. `hosted` now also carries the
  PostgreSQL drivers (same pins) and httpx; `postgres` stays for self-hosters
  on PostgreSQL who need neither Redis nor Supabase.

### Decisions a reviewer should know

- **Settings validator** accepts exactly two layouts: `single`+`local` and
  `multi`+`supabase` ("refuses other combinations"). `single`+`supabase`
  would need an identity→user mapping for a registry-less database, which no
  plan asks for; it is refused rather than half-supported.
- **Registry on its own metadata.** `PublicBase` (in `kaleta.db.base`) has a
  separate `MetaData`, so `Base.metadata.create_all` and `alembic/`
  autogenerate never see the registry; `alembic_public/` + `alembic_public.ini`
  migrate it with version table `alembic_version_public`.
- **Tenant migrations.** `alembic/env.py` takes `-x tenant_schema=`; on
  PostgreSQL it applies `version_table_schema`, `schema_translate_map` *and*
  `SET search_path` on the dedicated migration connection — data migrations
  use raw SQL, which the translate map does not rewrite. (ADR-35's pooler
  concern is about request connections; the migration connection is disposed
  right after.) Verified end to end against `postgres:16`.
- **Multi-tenant SQLite for dev and tests.** SQLite has no schemas, but an
  attached database's alias is a schema to SQLAlchemy. In `multi` mode on
  SQLite each schema is a file next to the main database
  (`<stem>.<schema>.db`); a tenant schema file is migrated as a standalone
  database (batch-mode reflection ignores the translate map). This lets the
  isolation tests and the e2e sign-up run in `verify.sh` without a PostgreSQL
  server; the CI `postgres-multi` job runs the same tests on real schemas.
  **Finding:** SQLite resolves an unqualified table name in *every* attached
  database, so one engine attaching all tenants let raw SQL (and a
  tenant-less "public" session) reach the first tenant's rows. Each tenant now
  gets its own SQLite engine attaching only `public` and itself; pinned by
  `test_raw_sql_in_a_tenant_session_never_reaches_another_tenant` and
  `test_the_public_session_cannot_see_tenant_tables`.
- **Fail closed.** `_SessionProxy.__call__` raises `TenantContextMissingError`
  (a `RuntimeError` → 500) in `multi` mode without a tenant;
  `AsyncSessionFactory.public()` is the only tenant-less session (registry,
  health). The UI middleware sets the tenant per page load; NiceGUI websocket
  events use a resolver the auth layer installs (`session_tenant_context`),
  because they pass no middleware.
- **API tenant resolution** is a dependency (`resolve_request_tenant`) every
  session dependency depends on, so it runs before the first session opens.
  A request with a bearer token is judged by that token alone — no fallback
  to the cookie — because the token's prefix has already chosen the schema
  the session opens in, and the cookie could belong to another tenant.
  No tenant → 401. `KALETA_API_TOKEN` (env bootstrap) is ignored in `multi`.
- **Attribution** (`UserOwnedMixin.user_id` from `TenantContext.member_user_id`)
  is one `before_flush` hook (`services/attribution.py`) rather than a line
  per service, so no service can forget it; an explicit `user_id` wins.
- **Revocation cache** is keyed by `(tenant_id, user_id)`: every schema
  numbers its `users` from 1.
- **Session keys.** `SESSION_TENANT_ID`, `SESSION_TENANT_SCHEMA`,
  `SESSION_AUTH_SUBJECT`, `SESSION_EMAIL` (and their `rotate_*` parking
  twins, scalar so the existing no-secrets test can see every value).
  `login_session(..., tenant=SessionTenant)` rather than an `Identity`, since
  the rotation route re-creates the session from parked scalars.
  `test_session_contents.py` was *extended* to drive the tenant writers and
  accept exactly the tenant values — no existing assertion was loosened.
- **Supabase provider.** Checks the access token's `sub`/`email` claims against
  the user object; the signature is not verified (token arrives straight from
  GoTrue over TLS in answer to our own request). The GoTrue session is ended
  right after sign-in: Kaleta's session is the session of record and nothing
  stores the refresh token. Sign-up for an existing address and password
  reset answer exactly as a success would (no account enumeration).
  Password reset needs the Supabase "Reset password" template pointed at
  `/reset-password?token_hash=…` (documented in `docs/deployment.md`); the
  page is new (`views/reset_password.py`) because the login page's "forgot
  password" link has to lead somewhere.
- **Raw SQL fixed where `multi` would break it:** `BackupService.export`
  (`SELECT *` now from the `Table`, still raw values — encrypted columns stay
  ciphertext), `restore` (`delete(Table)`, reflection with the tenant schema)
  and `DataService.clear_all` (`delete(transaction_tags)`). Per-account
  export in Settings → Data works per tenant (tested).
- **Single-tenant-only features in `multi`:** backup scheduler, event
  retention sweep, NBP startup fetch (its tables are per tenant; per-tenant
  sweeps are later work), the SQLite integrity card on `/housekeeping` (the
  rest of that page — duplicate merging — is kept), the install-wide NBP
  startup checkbox in Settings → Data, and the login page's ledger counts
  (no tenant before sign-in, and not a stranger's to see). There is no other
  SQLite-only card in Settings → Data: the backup card is the per-account
  JSON export/restore, which stays.
- **Health** reads through `get_public_session` (a tenant session would be a
  401 in `multi`); it reports `tenants_pending_migration` (null in `single`).
  `tests/unit/api/test_health.py` now overrides that dependency instead of
  `get_session` — fixture wiring only.
- **e2e** (`tests/e2e/test_tenant_signup.py`) runs the app in `multi` +
  `supabase` against `tests/fake_gotrue.py`, an in-process GoTrue stand-in
  whose verification link the test reads instead of a mailbox — the
  "verification stub" of §6. This exercises the real `SupabaseAuthProvider`
  over HTTP rather than swapping the provider class.

- **Acceptance criterion rewritten in form, not meaning.** The DoD gate
  treats a non-zero exit as a failed criterion, so "`KALETA_TENANCY=multi
  KALETA_AUTH_BACKEND=local … import kaleta.config` exits non-zero" was stated
  as `! <that command>`, which succeeds exactly when the import is refused.
  The same process-level check is also a unit test
  (`test_importing_the_config_with_multi_and_local_exits_non_zero`).

- **Modules beyond the listed Touchpoints, and why each exists:**
  - `schemas/identity.py` — `Identity`/`MfaRequired`/`SignUpResult` from §2.
    Here rather than in `auth/providers/` because `TenantService.provision`
    (a service) takes an `Identity`, and services may not import `kaleta.auth`.
  - `auth/sign_in.py` (`SignInFlow`) — §2 says `login_session` takes "an
    `Identity` plus the resolved tenant". Turning an identity into that
    (provision on first verified sign-in, check the tenant is active, record
    the login in the tenant's audit log, end the GoTrue session) is shared by
    the login and sign-up pages; one class keeps the views thin and tested.
  - `services/attribution.py` — §4's "services that create rows on
    `UserOwnedMixin` tables set `user_id` from it", as one flush hook.
  - `db/tenant_schemas.py` — schema-name minting/validation (§4 "never derived
    from the e-mail") and the SQLite attach helper.
  - `views/reset_password.py` + KAL-TEN-005 — §2's "forgot password" link has
    to land on a page that asks for the e-mail and, from the e-mailed link,
    for the new password. Covered end to end by
    `test_forgotten_password_is_reset_through_an_emailed_link`.
  - `tests/fake_gotrue.py` — the §6 "verification stub", as a GoTrue stand-in.

- **Found in the manual run against Supabase:** startup failed with
  `psycopg2 … invalid connection option "ssl"`. Revision reads use a sync
  psycopg2 engine built from `KALETA_DB_URL`, and `?ssl=require` (asyncpg's
  spelling, which `docs/deployment.md` prescribes) is not a libpq option.
  `_sync_url` now translates it to `sslmode`. Pre-existing for single-tenant
  installs on PostgreSQL with that URL too; fixed here because the hosted
  startup hits it first.

### Not done here (by scope)

- MFA on the hosted path (`auth-two-factor-hosted`), encryption and the
  `key_ring` slot's contents (`hosted-field-encryption`), members beyond the
  owner (`hosted-household-sharing`), deployment (`hosted-supabase-rollout`).
- A settings validation error echoes part of `KALETA_SECRET_KEY` (pydantic
  prints the input dict); pre-existing for every validator, filed in
  `docs/plans/chores.md`.

## Implementation

Landed on 2026-10-01 (PR #178).

| SHA | Author | Date | Message |
|---|---|---|---|
| `1689164` | Dawid Adamski | 2026-10-01 | Merge pull request #178 from DawidAdamski/plan/hosted-tenancy-foundation |

**Files changed:**
- .github/workflows/ci.yml
- alembic/env.py
- alembic/versions/f7a8b9c0d1e2_users_email_and_nullable_password.py
- alembic_public.ini
- alembic_public/README
- alembic_public/env.py
- alembic_public/script.py.mako
- alembic_public/versions/a0b1c2d3e4f5_tenant_registry.py
- docker-compose.yml
- docs/bdd.md
- docs/deployment.md
- docs/plans/chores.md
- docs/plans/hosted-tenancy-foundation.md
- docs/tech-stack.md
- pyproject.toml
- scripts/migrate_tenants.py
- src/kaleta/api/deps.py
- src/kaleta/api/v1/health.py
- src/kaleta/auth/middleware.py
- src/kaleta/auth/providers/__init__.py
- src/kaleta/auth/providers/base.py
- src/kaleta/auth/providers/local.py
- src/kaleta/auth/providers/supabase.py
- src/kaleta/auth/revocation_cache.py
- src/kaleta/auth/routes.py
- src/kaleta/auth/session.py
- src/kaleta/auth/sign_in.py
- src/kaleta/config/settings.py
- src/kaleta/config/setup_config.py
- src/kaleta/db/base.py
- src/kaleta/db/session.py
- src/kaleta/db/tenant_context.py
- src/kaleta/db/tenant_schemas.py
- src/kaleta/exceptions.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/main.py
- src/kaleta/models/tenant.py
- src/kaleta/models/user.py
- src/kaleta/schemas/health.py
- src/kaleta/schemas/identity.py
- src/kaleta/services/__init__.py
- src/kaleta/services/api_token_service.py
- src/kaleta/services/attribution.py
- src/kaleta/services/auth_service.py
- src/kaleta/services/backup_service.py
- src/kaleta/services/data_service.py
- src/kaleta/services/health_service.py
- src/kaleta/services/setup_service.py
- src/kaleta/services/tenant_service.py
- src/kaleta/views/auth_common.py
- src/kaleta/views/create_account.py
- src/kaleta/views/housekeeping.py
- src/kaleta/views/login.py
- src/kaleta/views/reset_password.py
- src/kaleta/views/settings/data_tab.py
- tests/e2e/test_tenant_signup.py
- tests/fake_gotrue.py
- tests/integration/test_tenant_isolation.py
- tests/tenancy_helpers.py
- tests/unit/api/test_health.py
- tests/unit/auth/test_session_contents.py
- tests/unit/auth/test_supabase_provider.py
- tests/unit/auth/test_tenancy_settings.py
- tests/unit/auth/test_tenant_context.py
- tests/unit/services/test_setup_service.py
- tests/unit/services/test_tenant_service.py
- uv.lock

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
