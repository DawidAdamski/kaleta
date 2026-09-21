---
plan_id: hosted-tenancy-foundation
title: Hosted — auth provider, tenant registry and schema per account
area: auth / db / setup
effort: large
status: draft
roadmap_ref: ../roadmap.md#2027-directions
---

# Hosted — auth provider, tenant registry and schema per account

## Intent

The hosted Kaleta must serve many accounts from one Supabase project
while the operator knows only each account's user id and e-mail, and the
self-hosted Podman/SQLite install must keep working exactly as it does.
This plan lays the multi-tenant foundation decided in
[ADR-35](../adr/035-hosted-multi-tenancy-and-user-held-encryption.md):
identity through Supabase Auth behind an `AuthProvider` interface, a
`public.tenants` registry, one Postgres schema per account selected per
request, and provisioning at sign-up. Encryption is the next plan
([`hosted-field-encryption`](hosted-field-encryption.md)); this plan
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
    [`hosted-household-sharing`](hosted-household-sharing.md); created
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
  [`hosted-household-sharing`](hosted-household-sharing.md). This plan
  only lays down the tables and the one-row-per-member rule.
- Migrating an existing single-tenant SQLite database into a hosted
  account (a later "import my self-hosted data" plan; the full-schema
  backup roundtrip from `backup-full-schema-roundtrip` is the seed).

## Acceptance criteria

- `uv run pytest tests/unit/auth tests/unit/services/test_tenant_service.py -q`
- `uv run pytest tests/integration/test_tenant_isolation.py -q` (Postgres job)
- `KALETA_TENANCY=multi KALETA_AUTH_BACKEND=local uv run python -c "import kaleta.config"` exits non-zero
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

(filled in as work progresses)
