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

Depends on [`test-suite-speed`](archive/test-suite-speed.md) (parallel Postgres
test runs exist before the SQLite runs are deleted).

## Delivery

Three pull requests on `plan/postgres-only*` branches, each green on its own
(decided 2026-10-10 after mapping the code: most SQLite code is the
`single` layout's, so the layout goes first and SQLite with it):

- **A — local logins on the registry layout** (§3, §4 and the CLI half of
  §4): additive; `single` keeps working. `KALETA_TENANCY=multi` +
  `KALETA_AUTH_BACKEND=local` becomes a valid instance.
- **B — one layout, PostgreSQL only** (§1, §2, §6): `single`, SQLite and the
  SQLite test runs go. Split in three on 2026-10-10, after the fast tier was
  seen passing on Postgres unchanged (3196 tests, 15 s — the same as SQLite):
  - **B1 — the test suite on PostgreSQL** (§6): the shared fixtures, the e2e
    servers and CI use Postgres only; `scripts/test_db.sh`; the SQLite `test`
    job goes. Production code untouched. Tests that build a SQLite file of
    their own to exercise SQLite-only code (pragmas, VACUUM backups, the setup
    wizard's file picker) stay until that code goes in B2/B3.
  - **B2a — what `single` alone did, on the registry layout** (decided with
    the maintainer 2026-10-10, see "Decisions for B2"): additive, `single`
    still works.
  - **B2b — one layout** (§2): `single` and `KALETA_TENANCY` go; encryption is
    always on. One PR in two kinds of commit (planned as two PRs on
    2026-10-10, merged back into one the same day: pinning `single` in the
    tests only to delete them a PR later was work thrown away): the tests on
    the registry layout — the suite's database is a registry with one family
    (`tests/conftest.py`), the API fixtures mint family tokens, every e2e
    server runs `local` with e-mail logins — and `single` with its code,
    settings and tests.
  - **B2c — NBP rates in `public`** (see "Decisions for B2"): after B2b, when
    every instance has a `public` schema (single-tenant SQLite has none).
    `public.nbp_rates` (one row per date and currency: the mid, PLN per
    unit; the inverse is derived) filled by `NbpRateService` on a public
    session, idempotent per date; `CurrencyRateService`'s readers
    (`get_rate_on`, `load_rates_for_currencies`, `list_pairs`,
    `list_recent_for_pairs`) see both tables, the family's row winning a
    tie; Settings lists NBP rows marked as such and without a delete
    button; `NbpRateScheduler` runs when `KALETA_NBP_FETCH` is on. NBP rows a
    family fetched before B2c stay in its `currency_rates` (they cannot be
    told from typed ones) — harmless, same values.
  - **B3 — SQLite out of `src/`** (§1): the dialect branches, `aiosqlite`, the
    refusal of a `sqlite` URL.
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

## Decisions for B2 (maintainer, 2026-10-10)

A map of every `single`/`multi` branch found fifteen things only `single`
does. Kept, on the registry layout:

- **NBP rates move to `public`.** Exchange rates are public data, the same
  for every family: one `public.nbp_rates` table (registry migration), one
  startup/scheduled fetch per instance, the Settings "fetch now" button
  unchanged. *Refined while building B2a:* the family's `currency_rates`
  stays, because it also holds the rates a member typed in and the ones
  recorded from their own currency transfers — those reveal the family's
  transactions and must not be shared. A lookup takes the latest rate on or
  before the date from either table, the family's own winning a tie.
  *Decided 2026-10-10 for B2c:* the instance switches the automatic fetch
  on with `KALETA_NBP_FETCH=true` (default off, KAL-FXR-003) — no UI, the
  admin panel may take it over later; when on, it fetches at start-up and
  then once a day.
- **Event retention loops over families.** One scheduler, once a day, sweeps
  each tenant schema in turn (events stay per family).
- **"The data passphrase is not the login password"** is checked against
  `public.local_identities` for `local` logins.
- **`tenant_admin.py reset-password EMAIL --disable-mfa`** turns the
  member's second factor off, as `kaleta --reset-password --disable-mfa` did.
- **`KALETA_API_TOKEN` stays** for headless use: on the registry layout it
  authenticates as the instance administrator in their family (refused when
  there is no administrator or no family yet). Like every bearer token, it
  reads encrypted fields only while that member has an unlocked session.

Dropped with `single`: the `/setup` database chooser, `config.json` and
"close database"; the SQLite safety copy before migrations (backups are the
operator's, ADR-38); scheduled SQLite backups; the login-page statistics; the
placeholder user and `/secure-app`; opening a browser on first run; username
(non-e-mail) logins; `encrypt_database.py`; a production install without
encryption.

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
- *No `must_change_password` enforcement yet*: the column exists (reserved,
  documented on the model) and nothing sets or reads it; the admin panel plan
  resets passwords that must be changed at the next sign-in.
  `tenant_admin.py reset-password` sets a new password and prints it once.

**After review (PR #194).**

- *First-run race*: "is the instance empty" + the insert, and the
  last-administrator guards, run under one decision lock — an
  `asyncio.Lock` in-process plus `pg_advisory_xact_lock` on Postgres
  (released by the commit or rollback). Two first sign-ups at once: one
  administrator, the other meets the closed registration. Tested.
- *Disabling ends what the login holds*: `kaleta.auth.local_logins.set_login_disabled`
  sets the flag, raises the member's session watermark, revokes their API
  tokens (`ApiTokenService.revoke_all`) and drops their unlocked key from this
  process's key ring. Another replica notices within the revocation cache's
  60 s TTL. Nothing calls it yet but the tests; the admin panel will.
- *Deleting a family keeps the administrator's login*: an instance
  administrator's login belongs to the instance, so `delete_identity` keeps
  it (their next sign-in starts a new, empty family); other members' logins
  go. Kept rather than refused so a multi-member deletion never stops
  half-way (the last-admin guard used to be able to raise mid-loop).
- *Input limits*: passwords over 1 024 characters are refused before
  hashing; an e-mail needs exactly one `@`, a local part, a domain and no
  whitespace.
- *Recovery hint*: the code prompt says "Each recovery code works once" for a
  local factor, not the Supabase sentence about turning the factor off.
- *Known limits, accepted*: (1) whoever reaches a fresh instance first
  becomes its administrator — the self-hosting guide must say to create the
  administrator with `tenant_admin.py create-login --admin` (or finish the
  first run) before exposing the instance; (2) the password form is
  throttled per client address, not per account, as on every backend today —
  a per-account throttle is a chore, not this plan.
- *Settings tests changed on purpose*: `test_tenancy_settings.py` asserted
  that `multi` + `local` is refused (the hosted-tenancy-foundation decision);
  ADR-38 reverses it, so both tests now assert it starts.
- *Not done in A*: `kaleta --reset-password` (single-tenant CLI) — part B
  replaces it with `tenant_admin.py reset-password`.

**Part B1 (branch `feat/postgres-only-part-b1`).**

- *One database for the suite*: `tests/suite_database.py` (was
  `xdist_postgres.py`) reads `KALETA_DB_URL`, defaulting to the server of
  `scripts/test_db.sh` (`postgresql+asyncpg://kaleta:kaleta@127.0.0.1:55432/kaleta`);
  a non-Postgres URL or a silent server ends the session with
  "Start one: ./scripts/test_db.sh up". `tests/conftest.py` migrates to head on
  every start (idempotent), so CI lost its separate `alembic upgrade head` step.
- *The e2e apps* each get a database of their own, `<db>_e2e_<name>`, dropped
  `WITH (FORCE)` and created again per run (`fresh_database_url`, synchronous
  because Playwright's sync API keeps a loop running in the test thread).
  Behind-the-app checks in the tenant e2e tests query Postgres (`query`), and
  "the schema file exists" became "the schema exists".
- *A finding SQLite hid*: the e2e seed helpers ran each call under its own
  `asyncio.run` on a pooled engine; asyncpg connections belong to the loop that
  opened them, so the second call failed. `_run_async_worker` now builds the
  engine for the call and disposes it before the loop ends.
- *SQLite-only code still in `src/`* keeps its tests: `IntegrityService`
  (`PRAGMA foreign_key_check`) runs on a `sqlite_session` fixture; the pragma,
  VACUUM-backup, migration-chain and CLI-reset tests build their own SQLite
  file and put the shared session factory back afterwards. They were skipped on
  the old Postgres job; now they run everywhere (3207 passed, 0 skipped).
  They go with that code in B2/B3.
- *Drivers*: `asyncpg` and `psycopg2-binary` joined the `dev` group (B3 moves
  them into the base install).
- *CI*: the SQLite `test` job is gone; `postgres` runs both tiers and spec
  coverage; the `valkey` job got a Postgres service for its e2e. The ruleset's
  required checks must drop `test` (maintainer).
- `verify.sh` and the pre-push hook run `./scripts/test_db.sh up` unless
  `KALETA_DB_URL` is set.

**Part B2a (branch `feat/postgres-only-part-b2a`, on top of B1).**

- *Retention* (KAL-OBS-004): `EventRetentionScheduler._purge_once` lists the
  families from the registry and purges each `active` one under
  `use_tenant`; a failing family is logged and the sweep goes on; suspended
  ones wait for `resume`. `main.py` starts it on both layouts.
- *Passphrase ≠ password* (KAL-TEN-020): `is_local_login_password(subject, …)`
  checks a `local:<id>` subject against `local_identities`; a Supabase subject
  answers no (nothing to compare with). The unlock view no longer skips the
  rule on `multi`.
- *`--disable-mfa`* (KAL-TEN-021): `MfaService.disable_for_admin(user_id)`
  shares `disable_all`'s body (bulk delete that works with unreadable
  secrets, sessions revoked, an `mfa_disabled_cli` audit row in the same
  transaction), narrowed to one member. `TenantAdminCli` takes a
  `tenant_session` factory for it.
- *`KALETA_API_TOKEN`* (KAL-TEN-022): `resolve_request_tenant` recognises the
  token before the `kt_` prefix check is refused, and resolves the oldest
  enabled instance administrator's membership (`env_token_membership`);
  `ApiTokenService` then authenticates it as that member. 401 until an
  administrator exists and has signed in once (no family before that).
- *NBP* moved out of B2a into B2c (above).
- *After review*: the env token also requires the administrator's membership
  to be `active` (a closed membership was accepted); it is compared as bytes
  (`compare_digest` raises on a non-ASCII `str`, so a crafted header gave 500,
  not 401 — the test fails on the old compare); a `kt_<digits>_…` value is
  documented as unusable; "oldest enabled administrator" moving to the next
  one is documented in `docs/deployment.md`; `--disable-mfa` refuses a
  suspended family instead of failing on its schema.

**Part B2b (branch `feat/postgres-only-part-b2b`, on top of B2a).**

- *The suite's family* (`tests/suite_family.py`): the suite database is a
  registry with one family, provisioned by Alembic once per session and
  emptied (every family table but `users`, then every user but the owner);
  each test runs under its `TenantContext` with `TEST_DATA_KEY` on it. The
  shared session pool is disposed and reconfigured after every test: asyncpg
  connections belong to the test's loop. The e2e conftest overrides that
  fixture with a sync no-op (Playwright owns the test thread's loop).
- *Raw SQL is not translated*: `schema_translate_map` rewrites only
  SQLAlchemy-built statements. Tests name the family's tables with
  `family_table()`; `search_path` was deliberately not used.
- *Two bugs `single` hid*: the transactions seeder cleared tags with a raw
  `DELETE FROM transaction_tags`, which hit `public` (no such table) in a
  family — now a Core `delete()`; `MfaService.disable()` checked the password
  against `users.password_hash`, which a registry login never has, so turning
  2FA off always failed — it now asks `LocalIdentityService` through the
  member's `auth_subject`.
- *A third, from Alembic-built families*: migration `a4e9b2f1c6d8` plants an
  English subscriptions tree (and `b9d4e2c8a1f5` eight tags) in every family
  schema, so the taxonomy seeder counted 4 categories and skipped — example
  data on a new family crashed in the transactions seeder. `count()` now
  ignores the subscriptions tree and `create()` files the Polish children under
  the existing root (KAL-PLT-010). `--replace` still clears whole tables, the
  planted defaults included, so the CLI replace test compares the second
  replace with the first.
- *KAL-AUTH-022 on local factors*: the registry provider answered "wrong code"
  when the factor was turned off under an open prompt; it now raises
  `ConflictError` from `mfa_challenge_verify` and `consume_recovery_code`,
  as Supabase does.
- *`kaleta-admin`*: `scripts/tenant_admin.py` moved to
  `kaleta.cli.tenant_admin` with a console script (the script stays as a
  wrapper). `reset-password` now also revokes the member's browser sessions
  (KAL-AUTH-028, which `kaleta --reset-password` did). `kaleta
  --reset-password` / `--disable-mfa` exit 2 naming it (KAL-TEN-023).
- *Removed with `single`*: the setup wizard and `config.json`, `/secure-app`
  and the placeholder user, username logins, the login-panel counts, the
  SQLite integrity panel, "Close database", the scheduled VACUUM backups and
  `KALETA_BACKUP_*` (§5 came forward: the scheduler only ever backed up the
  SQLite file), `encrypt_database.py`, `LocalKeyMaterial` (dropped by
  `s3t4u5v6w7x8`) and the per-install NBP-on-startup flag (back in B2c,
  KAL-FXR-003 `@planned`). Their scenarios are `@removed` with the reason.
- *The data-key resolver* (`install_data_key_resolver`) only answers outside a
  family's context now; whether anything still needs it is a chore.
- *Docs*: the pages that described removed commands and settings were
  corrected here; the full SQLite/packaging sweep stays in part C.

**Part B2c (branch `feat/postgres-only-part-b2c`, on top of B2b).**

- *`public.nbp_rates`* (`c2d3e4f5a6b7`): one row per date and currency, the
  mid only; `PLN → X` is derived as `1 / mid`, quantized to the six places
  `currency_rates.rate` keeps, so a derived inverse reads as a stored one did
  (KAL-FXR-001 keeps its literals). A unique `(date, currency)` makes the
  import idempotent; the daily fetch and the Settings button may both run.
- *Lookups*: `get_rate_on` takes the family's rate (direct, else inverted,
  as before) and the NBP one, the later date winning and the family's on a
  tie; `load_rates_for_currencies` merges both histories by date, the
  family's entries overwriting; `list_pairs` stays the family's alone, or
  Settings would list a pair for every NBP currency. Cross pairs (EUR→USD)
  come only from the family's table, as before.
- *Settings*: the list shows NBP rows with source "NBP" and no delete
  button; their keys are `<source>:<id>` (two tables, two id spaces). The
  fetch button writes through `with_public_session`.
- *`NbpRateScheduler`*: `KALETA_NBP_FETCH` (decided 2026-10-10: an
  environment switch, start-up plus daily) — web, app and api modes alike.
- *A finding*: `tests/tenancy_helpers.py` dropped the registry tables from a
  hand-kept list and missed the new one; it now drops whatever
  `PublicBase.metadata` knows.

## Implementation (filled by plan-archiver)
