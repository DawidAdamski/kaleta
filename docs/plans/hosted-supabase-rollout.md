---
plan_id: hosted-supabase-rollout
title: Hosted — Supabase project, app host, operations and Podman parity
area: ops / docs
effort: medium
status: draft
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

Depends on [`hosted-tenancy-foundation`](hosted-tenancy-foundation.md)
and [`hosted-field-encryption`](hosted-field-encryption.md).

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

(filled in as work progresses)
