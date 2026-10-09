---
plan_id: postgres-only
title: PostgreSQL only — one tenancy layout, local logins per family, SQLite removed
area: db / auth / ops
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#2027-directions
---

# PostgreSQL only — one tenancy layout, local logins per family, SQLite removed

## Intent

Carry out [ADR-38](../adr/038-postgresql-only-one-tenancy-layout.md):
Kaleta becomes one web application on PostgreSQL, run the same way on a
homelab and on the hosted instance — a `public` registry, one schema per
family, field encryption always on. Self-hosters keep password logins
that need no e-mail provider; they lose SQLite, the desktop window and the
app-managed backups. Every "keep SQLite compatibility" rule, dialect branch
and doubled CI run goes with them.

Depends on [`test-suite-speed`](test-suite-speed.md) (parallel Postgres
test runs exist before the SQLite runs are deleted).

## Delivery

Three pull requests on `plan/postgres-only*` branches, each green on its own
(decided 2026-10-10 after mapping the code: most SQLite code is the
`single` layout's, so the layout goes first and SQLite with it):

- **A — local logins on the registry layout** (§3, §4 and the CLI half of
  §4): additive; `single` keeps working. `KALETA_TENANCY=multi` +
  `KALETA_AUTH_BACKEND=local` becomes a valid instance.
- **B — one layout, PostgreSQL only** (§1, §2, §6): `single`, SQLite and the
  SQLite test runs go.
- **C — removals, packaging, docs** (§5, §7).

## Scope

### 1. Database

- PostgreSQL 16+ is the only supported `KALETA_DB_URL`. A `sqlite` URL is
  refused at start-up with one sentence pointing at the self-hosting
  guide. `aiosqlite` leaves the dependencies; the `postgres` extra folds
  into the base install (`asyncpg`).
- Remove the dialect branches: `kaleta.db.sql_compat`, the SQLite pragmas
  in `kaleta.db.session`, `_set_sqlite_foreign_keys` in `data_service`,
  `is_sqlite` checks, the SQLite FK-integrity panel in Housekeeping, the
  naive-datetime workaround in `auth_service`, and the SQLite branches in
  `tenant_schemas`, `types`, `setup_config`, `debug_info` and the
  services that grep shows (`grep -rli sqlite src/kaleta` lists 26 files
  on `ee7e52c`; the list must be empty at the end except the refusal
  message).
- Existing Alembic revisions stay (they run on Postgres today); new
  revisions stop using batch mode. Squashing the history is not in scope.

### 2. One tenancy layout

- `KALETA_TENANCY` is removed; every instance runs the registry + schema
  per family. Code under `if settings.multi_tenant` / `tenancy == "single"`
  collapses to the multi path. Start-up runs `ensure_multi_tenant_current`
  (registry, then every family), as hosted does today.
- `KALETA_ENCRYPTION=off` is accepted only with `KALETA_DEBUG=true`.
  `scripts/encrypt_database.py` (SQLite → encrypted in place) is removed.

### 3. Local logins on the multi layout

- `local` becomes a multi-tenant `AuthProvider`: identities (e-mail,
  argon2id hash, created/last-login, `disabled`) in a new registry table
  `public.local_identities`; the subject is the identity id. Sign-in,
  password change, admin reset (`kaleta --reset-password <email>`) and
  TOTP MFA keep working; MFA secrets move with the identity.
- No e-mail verification and no self-service password reset without
  SMTP; the instance admin resets passwords (CLI now, panel in
  [`instance-admin-panel`](instance-admin-panel.md)). With SMTP set, the
  existing reset flow is offered.
- `local` is valid with every layout; `supabase` stays hosted-only.
  The `fake` backend and its JSON identity file are removed;
  `compose.hosted-dev.yml` and the e2e tenant tests use `local`.

### 4. First run on an empty instance

- The setup wizard no longer picks a database file. On an empty registry
  it creates the **instance administrator** (e-mail + password, stored as
  a `local` identity with `is_instance_admin`) and the **first family**
  (name; the admin becomes its owner), then continues with the existing
  data-passphrase step and the budget wizard.
- `registration_mode` (`closed` | `invite` | `open`) is stored in the
  registry, default `closed` for `local`, `open` for `supabase`. With
  `closed`, `/signup` is not offered; `tenant_admin.py create-family
  --owner <email>` creates one from the CLI. The panel is the next plan.

### 5. Removed with SQLite

- `KALETA_MODE=app` (desktop window) — `web` and `api` stay. The PWA
  (ADR-17) is untouched.
- App-managed backups: `backup_service`, `scheduled_backup_service`,
  `backup_scheduler`, the safety copy before migrations, the
  `KALETA_BACKUP_*` settings and their Settings UI. The per-family export
  in Settings → Data stays.
- BDD scenarios for removed behaviour are retagged `@removed` with a
  one-line reason (not deleted), and their tests deleted with the code.

### 6. Tests and CI

- `tests/conftest.py`: Postgres only; without a reachable database the
  session fails with "start one: `./scripts/test_db.sh up`".
  `scripts/test_db.sh up|down` runs `postgres:16-alpine` under
  podman (or docker) on port 55432 with `fsync=off` and a tmpfs data dir.
- CI: the SQLite `test` job is deleted; one Postgres job runs the suite
  (`-n auto`, tiers from `test-suite-speed`).

### 7. Packaging and docs

- `docker-compose.yml` becomes Kaleta + `postgres:16-alpine` with a named
  volume and a generated password; `Containerfile` and
  `Containerfile.full` drop SQLite paths. `compose.hosted-dev.yml` stays
  for the Supabase-shaped stack.
- `AGENTS.md`, `docs/tech-stack.md`, `docs/getting-started.md`,
  `docs/deploy-local.md`, `README.md`: no SQLite, no `KALETA_TENANCY`,
  no `KALETA_BACKUP_*`, no `app` mode; the "Keep SQLite compatibility"
  pattern is replaced by "PostgreSQL 16+ only (ADR-38)".

### Not in scope

- Migrating any SQLite database (ADR-38: dropped).
- The instance admin panel UI ([`instance-admin-panel`](instance-admin-panel.md)).
- Household invites and approval ([`hosted-household-sharing`](hosted-household-sharing.md)).
- The self-hosting guide and backup routine ([`self-host-guide`](self-host-guide.md)).
- Squashing Alembic history; Postgres-only refactors of existing queries.

## Acceptance criteria

- `./scripts/test_db.sh up`
- `uv run pytest tests/unit tests/integration -n auto -q`
- `uv run pytest tests/e2e -q`
- `test -z "$(grep -rli sqlite src/kaleta --include='*.py' | grep -v config/settings.py)"`
- `test -z "$(grep -rn 'KALETA_TENANCY\|KALETA_BACKUP_' src docs AGENTS.md README.md --include='*.py' --include='*.md' | grep -v 'adr/0[0-3]' | grep -v plans/archive)"`
- `! grep -q aiosqlite pyproject.toml`
- `! grep -q "^  test:" .github/workflows/ci.yml`
- `podman compose -f docker-compose.yml config`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `[manual]` `podman compose up` on an empty volume: first run creates the admin and the first family, the data passphrase is asked, a transaction round-trips, `podman compose restart kaleta` asks for `/unlock` again.

## Touchpoints

`src/kaleta/config/settings.py`, `src/kaleta/config/setup_config.py`,
`src/kaleta/db/{base,session,sql_compat,tenant_schemas,types}.py`,
`src/kaleta/auth/providers/{__init__,local,fake}.py`,
`src/kaleta/services/{auth_service,setup_service,data_service,tenant_service,integrity_service,backup_*,scheduled_backup_service}.py`,
`src/kaleta/views/{setup,housekeeping,settings*}.py`, `src/kaleta/main.py`,
`alembic_public/versions/` (new: `local_identities`, `registration_mode`,
`is_instance_admin`), `scripts/{tenant_admin,encrypt_database,reset_demo}.py`,
`tests/**`, `docker-compose.yml`, `Containerfile*`, `compose.hosted-dev.yml`,
`.github/workflows/ci.yml`, `pyproject.toml`, `AGENTS.md`, `docs/*.md`,
`docs/bdd.md`, i18n `en.json` / `pl.json`.

## Open questions

- `users` rows in each tenant schema keep display name and attribution;
  only the password hash moves to the registry. Default: yes — the hash
  is identity, the row is membership.
- Does `api` mode (headless) need the first-run flow? Default: the CLI
  (`tenant_admin.py create-admin`) covers it.
- `reset_demo.py` keeps working with `--tenant`; its single-tenant path
  goes. Default: yes.

## Implementation notes

**Part A (branch `plan/postgres-only`).**

- *Registry*: `alembic_public` revision `b1c2d3e4f5a6` adds
  `public.local_identities` (e-mail, argon2id hash, `is_instance_admin`,
  `disabled`, `must_change_password`, `created_at`, `last_login_at`) and
  `public.instance_settings` (key/value; `registration_mode`). Models
  `LocalIdentity`, `InstanceSetting` sit beside `Tenant` on `PublicBase`;
  `RegistrationMode` is in `kaleta.schemas.identity`.
- *Subject*: `local:<identity id>` — never collides with a GoTrue UUID, so
  `tenant_members.auth_subject` stays one namespace.
- *Provider*: `RegistryAuthProvider` (`name = "local"`) is built when
  `tenancy == "multi"` and the backend is `local`; the single-tenant
  `LocalAuthProvider` stays until part B. Providers gained `email_login`
  so views stop inferring the form from the name.
- *Second factor*: kept in `user_mfa` inside the family's schema
  (`MfaService`), not moved to the registry. A right password for a member
  with MFA on answers `MfaRequired(factor_id="local")`; the code is checked by
  `RegistryAuthProvider.mfa_challenge_verify` inside that family, so the login
  prompt takes the same `SignInFlow.verify_code` path as a hosted sign-in.
  A recovery code goes through `RegistryAuthProvider.consume_recovery_code`
  (crossed off, factor kept — as on a single-tenant install).
- *First run*: an empty `local_identities` makes `/login` redirect to
  `/create-account`, titled "Set up this Kaleta"; that sign-up is the
  administrator; its first sign-in provisions the first family (the same
  `TenantService.provision`). Later sign-ups need `registration_mode=open`;
  the default is `closed`. The plan's "first family name" field is not there:
  `tenants.name` stays empty until the admin panel (or household plan) names it.
- *No `must_change_password` enforcement yet*: the column exists; the admin
  panel plan resets passwords that must be changed at the next sign-in.
  `tenant_admin.py reset-password` sets a new password and prints it once.
- *Settings tests changed on purpose*: `test_tenancy_settings.py` asserted
  that `multi` + `local` is refused (the hosted-tenancy-foundation decision);
  ADR-38 reverses it, so both tests now assert it starts.
- *Not done in A*: `kaleta --reset-password` (single-tenant CLI) — part B
  replaces it with `tenant_admin.py reset-password`.

## Implementation (filled by plan-archiver)
