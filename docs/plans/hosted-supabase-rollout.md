---
plan_id: hosted-supabase-rollout
title: Hosted — Supabase project, app host, operations and Podman parity
area: ops / docs
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#2027-directions
---

# Hosted — Supabase project, app host, operations and Podman parity

## Intent

Take the multi-tenant, encrypted Kaleta from a CI matrix to a running
service: one Supabase project configured for Auth and Postgres, one app
host running `kaleta:full` in `multi` mode, migrations and the demo
tenant operated from scripts, and documentation that keeps the Podman
self-host path first-class. Also removes the operator-side footguns
the earlier plans introduce (session storage on disk, single-process
keyring) so the hosted instance can be restarted without surprises.

Depends on [`hosted-tenancy-foundation`](archive/hosted-tenancy-foundation.md)
and [`hosted-field-encryption`](archive/hosted-field-encryption.md).

## Scope

### 1. Supabase project

- Auth: e-mail provider on, "confirm e-mail" on, password minimum 8,
  redirect URLs = `KALETA_PUBLIC_URL/login`; custom SMTP (Resend or
  Postmark) so verification and reset mails come from the Kaleta domain
  — Supabase's default sender is rate-limited to a handful per hour.
  E-mail templates (verification, reset) in `deploy/supabase/templates/`,
  in English and Polish.
- Database: `public` holds only `tenants` and `alembic_version_public`;
  the app role is a dedicated Postgres role with `CREATE` on the
  database (for schemas) and no superuser; Row Level Security is left
  off because the app never uses the Supabase Data API — PostgREST and
  the anon key are unused and the `public` schema is removed from the
  exposed schemas list.
- Connection: app on the transaction pooler (6543), migrations on the
  direct connection — as in `docs/deployment.md` today. Confirm pool
  sizes: `pool_size=5, max_overflow=5` per app process.
- Point-in-time recovery or daily backups on the Supabase plan;
  document the retention.

### 2. App host

- One container, `kaleta:full`, `KALETA_TENANCY=multi`,
  `KALETA_AUTH_BACKEND=supabase`, HTTPS at the edge. Candidates stay as
  in `deployment.md` (Fly.io, Railway, Hetzner VPS); the decision is
  recorded in implementation notes, not here.
- NiceGUI `app.storage.user` is file-based per process: set
  `NICEGUI_REDIS_URL` (Upstash / host Redis) so a restart or a second
  replica keeps sessions — or document "single replica, sessions
  survive restarts via the storage file on a persistent volume". Either
  way the `KeyRing` is in-memory only, so a restart locks every tenant
  and users re-enter the passphrase; the login page says why.
- Health: `/api/v1/health` gains `tenancy`, `auth_backend`,
  `tenants_pending_migration`, `keyring_sessions` (count only).
- Startup ordering: migrate `public` → migrate tenants → start.
  A tenant whose migration fails is marked `status=suspended` and the
  rest continue; the health endpoint lists suspended tenant ids.

### 3. Scripts and jobs

- `scripts/migrate_tenants.py` (from the foundation plan) as the deploy
  hook; `scripts/reset_demo.py` gains `--tenant demo` and provisions
  the demo tenant if missing; nightly cron unchanged otherwise.
- `scripts/tenant_admin.py`: `list` (tenants with member count),
  `members <id>`, `suspend <id>`, `delete <id>` (drops the schema,
  deletes every member's Supabase auth user through the service-role
  key, writes an audit line to stdout). Deletion is also
  reachable from Settings → Data → "Delete my account" (owner only,
  two-step confirm, passphrase required, lists the members who lose
  access), which is the GDPR path. A non-owner member's GDPR path is
  "Leave household" (sharing plan §3), which removes their identity.
- `scripts/hosted_smoke.sh`: sign up a throwaway identity through
  GoTrue, log in, unlock, `POST` one transaction, `GET` it back, delete
  the tenant. Run after every deploy.

### 4. Podman parity

- `docker-compose.yml`: default service unchanged (SQLite, single,
  local). Add `compose.hosted-dev.yml` with `postgres:16` + Kaleta in
  `multi` mode + `FakeAuthProvider` (`KALETA_AUTH_BACKEND=fake`,
  refused unless `KALETA_DEBUG=true`) so the hosted flow can be
  exercised on a laptop with `podman compose -f compose.hosted-dev.yml up`.
- `docs/getting-started.md` states plainly: self-hosted = Podman +
  SQLite, single user, encryption optional; hosted = Supabase, many
  accounts, encryption always on. Same image, different env.

### 5. Documentation

- `docs/deployment.md` rewritten around `multi` mode; the demo section
  moves to the end.
- `docs/privacy.md` (renamed from `privacy-events.md`): what the
  operator stores about an account (user id, e-mail, key-wrapping
  material, anonymous error events, optional bug reports), what is
  encrypted, what is visible, retention, deletion.
- `README.md`: hosted instance link and the one-paragraph privacy
  promise; `docs/roadmap.md` 2027 → "managed hosting" marked in
  progress; `docs/tech-stack.md` env table extended.

### Not in scope

- Billing, plans, feature flags (roadmap Q4 §5).
- Multi-region or more than one app replica beyond what §2 documents.
- Import of a self-hosted SQLite database into a hosted account.

## Acceptance criteria

- `./scripts/hosted_smoke.sh` against the hosted-dev compose stack
- `uv run pytest tests/unit/api/test_health.py -q` — new fields present
- `uv run pytest tests/unit/scripts/test_tenant_admin.py -q`
- `podman compose -f compose.hosted-dev.yml config` (valid file)
- `grep -q "KALETA_TENANCY" docs/tech-stack.md`
- `grep -q "What the operator can see" docs/privacy.md`
- `./scripts/verify.sh`
- `[manual]` Deploy to the chosen host, run `scripts/hosted_smoke.sh`
  against the public URL, confirm the verification e-mail arrives from
  the Kaleta domain, restart the container and confirm the session
  survives and `/unlock` is asked again.

## Touchpoints

`deploy/supabase/templates/*.html` (new), `compose.hosted-dev.yml`
(new), `scripts/{migrate_tenants,tenant_admin,hosted_smoke}.{py,sh}`,
`scripts/reset_demo.py`, `src/kaleta/api/v1/health.py`,
`src/kaleta/schemas/health.py`, `src/kaleta/services/health_service.py`,
`src/kaleta/main.py` (startup ordering), `src/kaleta/auth/providers/fake.py`
(new, debug only), `src/kaleta/views/settings/data_tab.py` (delete
account), `docs/{deployment,privacy,getting-started,tech-stack,roadmap}.md`,
`README.md`.

## Open questions

- App host: Fly.io keeps the earlier recommendation; Hetzner is cheaper
  long-term and Dawid runs infrastructure already. Decide on
  operational time, not price.
- Redis for NiceGUI storage versus a persistent volume — Redis is the
  cleaner answer if a second replica is ever wanted; the volume is
  enough for one.
- Should the public demo stay in `multi` mode (one tenant, published
  passphrase) or move to a separate `single` instance with encryption
  off? The latter keeps the demo simple and the privacy statement of the
  real instance uncomplicated.

## Implementation notes

**Open questions, defaults taken (2026-10-03, goal mode — no questions asked).**

- *App host*: **Fly.io** — the earlier recommendation, and the one that costs
  the least operating time (container + volume + TLS in one place). Hetzner
  stays the cheaper move once the service is stable. Not wired into the repo:
  `docs/deployment.md` documents the env block for any container host.
- *Redis vs a persistent volume*: **a persistent volume, one replica.** A
  mount at `~/.kaleta` keeps NiceGUI's session files (and nothing secret)
  across restarts; `KALETA_REDIS_URL` stays the documented path to a second
  replica, which §2 does not ask for. Verified on `compose.hosted-dev.yml`
  (named volume at `/root/.kaleta`): signed in, unlocked, `restart kaleta` →
  `keyring_sessions` 1 → 0, still signed in, sent to `/unlock`, unlocks again.
- *Public demo*: **recommended as a separate `single` instance, encryption
  off** (simplest; keeps the hosted privacy statement clean) —
  `docs/deployment.md` § Public demo says so. §3's `reset_demo.py --tenant demo`
  is implemented anyway, because Scope asks for it: it signs the demo owner in
  at the provider (the `fake` backend signs it up; with Supabase the identity
  is created once, auto-confirmed, in the dashboard), provisions the account
  if missing, sets up/opens the published passphrase and reseeds in place.
  `--tenant` is refused on a single-tenant install and vice versa.

**Decisions a reviewer should know.**

- *`fake` backend*: `kaleta.auth.providers.fake.FakeAuthProvider`, accepted only
  with `KALETA_TENANCY=multi` **and** `KALETA_DEBUG=true` (settings validator).
  Every address is confirmed at sign-up (sign-up signs in at once); identities
  are argon2 hashes in `~/.kaleta/fake-auth.json` (0600) with a subject derived
  from the address (uuid5), so a restarted container keeps them. No reset, magic
  link or MFA — those raise `ValidationError` with a sentence. Views now treat
  any provider but `local` as the hosted e-mail form; the "Forgot password" /
  magic-link links stay Supabase-only.
- *Startup ordering*: `ensure_multi_tenant_current` returns a
  `TenantMigrationRun(migrated, suspended)`. The registry failing still stops
  startup; a tenant failing is logged, marked `suspended` (one `UPDATE` on the
  registry) and the loop continues. It is **not** un-suspended automatically
  when a later migration succeeds — an operator suspension must not be undone
  by a restart — hence `tenant_admin.py resume`, a fifth command beyond the
  four §3 lists, and `TenantService.resume` (only from `suspended`).
  `migrate_tenants.py` exits 3 when it suspended an account.
- *Health*: `tenancy`, `auth_backend`, `keyring_sessions` (`KeyRing.count()`),
  `suspended_tenants` (ids; `null` in `single`). Unauthenticated, as before —
  the ids are registry integers, nothing about the people.
- *Deletion order* (`AccountDeletionService`): every member's identity is
  removed at the provider **first**, then the schema and registry rows. A
  provider failure therefore drops nothing and the command can be repeated;
  the opposite order could leave a live identity that would re-provision an
  empty account at its next sign-in. `tenant_admin.py delete` needs `--yes`
  and prints one JSON audit line (account id, schema, identity count — no
  e-mail). SQL echo is off in the script even under `KALETA_DEBUG` so stdout
  stays parseable.
- *Settings → Data → Delete my account*: orchestration in
  `kaleta.auth.account_deletion` (views may not open sessions). Owner-only
  (button hidden otherwise, and re-checked on delete), step 1 lists members
  with their role, step 2 needs the data passphrase (`KeyService.open`; a wrong
  one deletes nothing), then every member's key-ring entry is dropped and the
  browser signed out. Other members' open sessions are not chased: their
  identities and schema are gone, so their next request fails and their next
  sign-in is refused.
- *"The login page says why"*: the explanation is on **`/unlock`**
  (`unlock.restart_note`), because with sessions surviving a restart that is
  the page people land on — and also after a fresh login. Tested in e2e
  (KAL-TEN-012); the restart itself is KAL-TEN-013 `@manual`.
- *Connections* (§1): PostgreSQL engines now use `pool_size=5`,
  `max_overflow=5`, `pool_pre_ping=True`; with asyncpg, `statement_cache_size=0`
  and a fresh `prepared_statement_name_func` name per statement, so a
  transaction-mode pooler (6543) can never hand a statement to a connection
  that did not prepare it. Ran the tenancy suites against `postgres:16`
  (29 passed).
- *Images*: `Containerfile.full` installs the `hosted` extra and copies
  `alembic_public/` + `alembic_public.ini` — without them `kaleta:full` could
  not start in `multi` mode at all. `docker-compose.yml` is unchanged.
- *`compose.hosted-dev.yml`*: `postgres:16-alpine` with
  `deploy/postgres/init-app-role.sql` creating the non-superuser `kaleta_app`
  role the app connects as (the same statements as the Supabase SQL editor
  step); app on port 8090 (`KALETA_HOSTED_DEV_PORT`).
- *Smoke*: `scripts/hosted_smoke.sh [URL]` → `scripts/hosted_smoke.py`
  (Playwright, dev group). No URL: brings the dev stack up, runs, `down -v`.
  The identity: `fake` → sign-up page; `supabase` → GoTrue admin API with the
  service-role key (`email_confirm: true`), so no mailbox is needed. Steps:
  health → identity → data passphrase → API token (Settings → Security) →
  `POST`/`GET` a transaction (description round-trips through encryption) →
  Delete my account → old password refused. Passed against the dev stack.
- *E-mail templates*: Supabase sends one template per project to everyone, so
  "in English and Polish" is **one bilingual file per template** (Polish
  first), not a pair. A magic-link template is included too: the login page
  already offers magic links.
- *Privacy*: `docs/privacy.md` gained "What the operator stores about an
  account" and "Deletion and retention". Writing it surfaced that error events
  and bug reports live in each tenant schema and are **not swept** in `multi`
  mode — stated in the doc, added to `docs/plans/chores.md` rather than fixed
  here (out of scope).
- *Chores added*: missing `.containerignore` (180 MB build context), the
  per-tenant retention sweep.
- *Test-only change*: `tests/fake_gotrue.py` gained the admin
  `DELETE /admin/users/{id}` endpoint (service-role key checked) so the e2e
  module can cover the Supabase deletion path.

**Scenarios.** New: KAL-TEN-008…014 (013 `@manual`); KAL-API-004 extended.
