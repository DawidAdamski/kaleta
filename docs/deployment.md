# Hosted deployment (Supabase + one app container)

How to run the hosted Kaleta: many accounts on one instance
(`KALETA_TENANCY=multi`, [ADR-35](adr/035-hosted-multi-tenancy-and-user-held-encryption.md)),
with **Supabase** for sign-in and PostgreSQL and **one container** of
`kaleta:full` for the app. Every account lives in a schema of its own and is
encrypted under a key only its members' data passphrases open.

Self-hosting is a different, simpler path — Podman + SQLite, one household —
described in [getting-started.md](getting-started.md#docker-podman). It is
the same image; only the environment differs. For localhost autostart
(launchd / systemd) see [deploy-local.md](deploy-local.md).

## Overview

| Component | Role |
|---|---|
| Supabase Auth (GoTrue) | Sign-up, e-mail confirmation, password reset, magic links, second factor |
| Supabase Postgres | `public` registry of accounts + one schema `t_<12 hex>` per account |
| App host | One `kaleta:full` container, HTTPS terminated at the edge |
| Redis-compatible store (optional) | Shared sessions, needed only for a second replica |
| `scripts/migrate_tenants.py` | Deploy hook: registry, then every account, to head |
| `scripts/hosted_smoke.sh` | Run after every deploy: one throwaway account end to end |
| `scripts/tenant_admin.py` | The operator's commands: list, members, suspend, resume, delete |

Secrets (`KALETA_DB_URL`, `KALETA_SECRET_KEY`, the Supabase keys, SMTP
credentials) are **env-only** — never commit them.

## 1. Supabase project

### Auth

In *Authentication → Providers → Email*:

- E-mail provider **on**, **Confirm email on**, minimum password length **8**
  (Kaleta asks for 8 too).
- *URL configuration*: **Site URL** = `KALETA_PUBLIC_URL`; **Redirect URLs**
  = `KALETA_PUBLIC_URL/login` and `KALETA_PUBLIC_URL/auth/magic`.
- **Custom SMTP** (Resend or Postmark) with a sender on the Kaleta domain.
  Supabase's built-in mailer allows only a handful of messages an hour per
  project — not enough for sign-ups and resets. Kaleta adds its own limit of
  one confirmation per address a minute.

**E-mail templates** live in [`deploy/supabase/templates/`](../deploy/supabase/templates/):
paste each file into *Authentication → Emails*. Supabase sends one template
to everyone, whatever their language, so each carries Polish and English.

| Template | File | Link it must contain |
|---|---|---|
| Confirm signup | `confirm-signup.html` | `{{ .ConfirmationURL }}` — GoTrue verifies, then redirects to `/login?reason=verified` |
| Reset password | `reset-password.html` | `{{ .SiteURL }}/reset-password?token_hash={{ .TokenHash }}` |
| Magic Link | `magic-link.html` | `{{ .SiteURL }}/auth/magic?token_hash={{ .TokenHash }}` |

"Resend confirmation e-mail" reuses *Confirm signup*. A magic link never
creates an account (Kaleta asks with `create_user: false`).

### Database

- **`public` holds only the registry**: `tenants`, `tenant_members`,
  `tenant_invites` and the version table `alembic_version_public`. No
  financial data, no user-written text in the clear.
- **A dedicated application role**, not `postgres`: it may create schemas
  (one per account) and the registry tables in `public`, nothing more. Run
  once in the SQL editor, with a real password — the same statements
  `compose.hosted-dev.yml` runs from
  [`deploy/postgres/init-app-role.sql`](../deploy/postgres/init-app-role.sql):

  ```sql
  CREATE ROLE kaleta_app LOGIN PASSWORD '<long random>' NOSUPERUSER NOCREATEDB NOCREATEROLE;
  GRANT CONNECT, CREATE ON DATABASE postgres TO kaleta_app;
  GRANT USAGE, CREATE ON SCHEMA public TO kaleta_app;
  ```

- **Row Level Security stays off, and the Data API is unused.** Kaleta never
  talks to PostgREST and never hands the anon key a table: isolation is the
  schema per account plus the encryption key per account. Remove `public`
  from *Settings → API → Exposed schemas* so nothing is reachable through the
  Data API even by mistake.

### Connections

The app and the migrations use different endpoints:

```env
# App runtime — the transaction pooler (port 6543)
KALETA_DB_URL=postgresql+asyncpg://kaleta_app.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?ssl=require
# Migrations (scripts/migrate_tenants.py) — the direct connection (port 5432)
KALETA_DB_URL=postgresql+asyncpg://kaleta_app:[password]@db.[project-ref].supabase.co:5432/postgres?ssl=require
```

Each app process opens at most **ten** connections (`pool_size=5`,
`max_overflow=5`). asyncpg's prepared-statement cache is off and every
statement gets a fresh name, because a transaction-mode pooler hands each
transaction whichever server connection is free; on the direct connection
that costs a re-parse per query and nothing else.

### Backups

Supabase backs the database up; Kaleta's own SQLite backups do not run in
`multi` mode. On the Pro plan daily backups are kept for **7 days**;
**point-in-time recovery** is an add-on with 7, 14 or 28 days of history.
Pick one before the first real account signs up and write the retention into
the instance's runbook — together with the warning that restoring the
database also restores any account deleted since (see
[privacy.md](privacy.md#deletion-and-retention)).

## 2. App host

One container, `kaleta:full` (it ships the `hosted` extra and the registry
migrations), HTTPS at the edge, `KALETA_HOST=0.0.0.0` inside:

```env
KALETA_TENANCY=multi
KALETA_AUTH_BACKEND=supabase
KALETA_DB_URL=postgresql+asyncpg://...:6543/postgres?ssl=require
KALETA_SUPABASE_URL=https://<project-ref>.supabase.co
KALETA_SUPABASE_ANON_KEY=<anon key>
KALETA_SUPABASE_SERVICE_ROLE_KEY=<service_role key>   # account deletion; never sent to a browser
KALETA_PUBLIC_URL=https://app.example
KALETA_SECRET_KEY=<long random string>
KALETA_SESSION_COOKIE_SECURE=true
KALETA_HOST=0.0.0.0
KALETA_PORT=8080
```

Encryption needs no variable: `multi` always encrypts, and
`KALETA_ENCRYPTION=off` is refused outside `KALETA_DEBUG=true`.

**Which host.** Fly.io (container deploy, one volume, TLS included), Railway
(similar) or a Hetzner VPS (cheapest, more to operate yourself). Choose by
the operating time it costs, not the price; the choice is recorded in the
`hosted-supabase-rollout` plan's implementation notes rather than here.

**Cookies.** `KALETA_SESSION_COOKIE_SECURE=true` marks the session cookie
`Secure`: the browser never sends it over plain http, so login silently stops
working on an install that is not served over TLS. Leave it `false` for local
or plain-http use. `KALETA_SESSION_COOKIE_SAMESITE` is `lax` (default) or
`strict`; `strict` drops the cookie on any navigation that starts outside the
app, e-mail confirmation links included. The cookie is `kaleta_session` and
expires after `KALETA_SESSION_TTL_HOURS`.

### Startup order and health

On start a `multi` instance migrates the registry (`alembic_public/`), then
every account's schema, then serves. The registry failing stops the start —
nothing works without it. **One account failing to migrate does not**: that
account is marked `suspended` (its members are refused at sign-in), the
error is logged, and every other account starts. Fix the cause, run
`scripts/migrate_tenants.py`, then `scripts/tenant_admin.py resume <id>`.

`GET /api/v1/health` (no authentication) reports:

| Field | Meaning |
|---|---|
| `database_ok`, `migrations_pending` | The database answers; registry or any account behind head |
| `tenancy`, `auth_backend` | `multi` / `supabase` on the hosted instance |
| `tenants_pending_migration` | How many account schemas are behind head |
| `suspended_tenants` | Ids of suspended accounts — those a failed migration suspended among them |
| `keyring_sessions` | How many sessions hold an unlocked data key in this process (a count) |

### Sessions, restarts and replicas

A browser's session — who is signed in and when, plus preferences such as
dark mode — lives in NiceGUI's `app.storage.user`; the failed-login counters
live in the rate limiter. Where both are kept is one variable:

```env
KALETA_REDIS_URL=redis://:password@valkey-host:6379/0
```

| `KALETA_REDIS_URL` | Sessions | Login rate limiter |
|---|---|---|
| unset (default) | one JSON file per browser in `~/.kaleta/nicegui` | a dict in the process |
| set | keys `kaleta:user-<id>` (via `NICEGUI_REDIS_URL`) | keys `kaleta:login:<ip>`, `kaleta:mfa:<user id>` |

**One replica on a persistent volume (the hosted default).** Mount a volume
at `~/.kaleta` (`/root/.kaleta` in the image): sessions survive a restart in
the files, and a restart resets the failed-login counts. No Redis needed.

**Two or more replicas.** Set `KALETA_REDIS_URL` on every replica, all
pointing at the same server — Valkey is the recommended one (BSD-licensed;
CI runs `valkey/valkey:8`), Redis or a managed Redis-compatible service work
the same. Keep **sticky sessions** on the load balancer: NiceGUI syncs
sessions between processes after the write, and a hosted two-factor sign-in
keeps the provider's `aal1` session in the memory of the replica that took
the password. More than one replica is not part of the first rollout.

**A restart locks every account.** The unlocked data keys live in the
process's memory only (the `KeyRing`), never on disk or in Redis. After a
restart or deploy every member keeps their session but lands on `/unlock`,
which says why, and types the data passphrase again. `keyring_sessions` in
the health probe drops to `0` and climbs as people unlock.

**Permissions.** Nothing secret goes into session storage — no password
hash, TOTP secret, recovery code or key (ADR-035, enforced by
`tests/unit/auth/test_session_contents.py`). Kaleta runs with umask `077`:
`~/.kaleta/nicegui` is `0700` and each session file `0600`. A sidecar that
reads the volume under another uid (a backup shipper) cannot read new files;
run it under Kaleta's uid.

**Not in `multi` mode:** the setup wizard, `~/.kaleta/config.json`, scheduled
SQLite backups, the NBP startup fetch and the SQLite integrity check. The event
retention sweep visits every active family once a day. `KALETA_API_TOKEN`
authenticates as the instance administrator (local logins only), in their
family.

## 3. Operations

### Deploy

1. Migrate first, against the direct connection — the same job startup runs,
   so a slow migration does not hold the new container's health check:

   ```bash
   KALETA_TENANCY=multi KALETA_AUTH_BACKEND=supabase KALETA_DB_URL=<direct url> \
     KALETA_SUPABASE_URL=... KALETA_SUPABASE_ANON_KEY=... \
     uv run python scripts/migrate_tenants.py          # --check: report only
   ```

   Exit status 0 all at head, 1 (`--check`) something behind, 2 the registry
   failed, 3 an account failed and was suspended.

2. Roll out the new image.
3. Smoke-test the public URL:

   ```bash
   KALETA_SUPABASE_URL=https://<project-ref>.supabase.co \
   KALETA_SUPABASE_SERVICE_ROLE_KEY=<service_role key> \
     ./scripts/hosted_smoke.sh https://app.example
   ```

   It creates a throwaway identity, already confirmed, through GoTrue's admin
   API; signs in; chooses a data passphrase; mints an API token; `POST`s one
   transaction and `GET`s it back (its description round-trips through the
   encryption); deletes the account from Settings → Data; and checks the old
   password is refused. It needs the dev dependencies and Playwright's
   Chromium on the machine that runs it. A run that fails after sign-up
   prints the address it left behind.

### Accounts

`scripts/tenant_admin.py` reads only the registry — e-mail addresses,
roles, statuses — never an account's data:

```bash
uv run python scripts/tenant_admin.py list               # id, schema, status, members, last seen
uv run python scripts/tenant_admin.py members 12         # e-mail, role, status
uv run python scripts/tenant_admin.py suspend 12         # refuse its sign-ins
uv run python scripts/tenant_admin.py resume 12          # let them in again
uv run python scripts/tenant_admin.py delete 12 --yes    # identities, schema, rows
```

`delete` removes every member's Supabase identity first (with the
service-role key), then drops the schema and the registry rows, and prints
one JSON audit line — keep it. If the provider cannot remove an identity,
nothing is dropped and the command can simply be run again.

**The owner's own path (GDPR)** is Settings → Data → *Delete my account*:
owner only, two confirmations, the data passphrase required, and the list of
members who lose access shown first. It does exactly what `delete` does. A
member who is not the owner leaves the household instead.

## 4. The hosted flow on a laptop

`compose.hosted-dev.yml` runs the same layout locally: `postgres:16` with the
non-superuser `kaleta_app` role, and `kaleta:full` in `multi` mode with
`KALETA_AUTH_BACKEND=fake` — a debug stand-in for Supabase Auth that confirms
every address at sign-up and keeps identities in a file. It is refused unless
`KALETA_DEBUG=true`, so it cannot reach a real deployment by accident.

```bash
podman compose -f compose.hosted-dev.yml up -d --build   # http://localhost:8090
./scripts/hosted_smoke.sh http://localhost:8090
podman compose -f compose.hosted-dev.yml down -v
```

`./scripts/hosted_smoke.sh` with no URL does all three (`KALETA_SMOKE_KEEP=1`
leaves the stack up). The app's `~/.kaleta` is a named volume, so
`podman compose -f compose.hosted-dev.yml restart kaleta` shows the restart
behaviour: still signed in, asked to unlock again.

## Encrypting an existing self-hosted database

Self-hosted (`single` mode) installs run with `KALETA_ENCRYPTION=off` by
default. To protect an existing SQLite or PostgreSQL database with
field-level encryption (see [tech-stack.md](tech-stack.md#field-level-encryption)
and [privacy.md](privacy.md#encryption)):

1. **Back up first.** The script takes its own plaintext snapshot before
   touching anything, but keep your own backup too.
2. Run the one-off migration:

   ```bash
   KALETA_ENCRYPTION=passphrase uv run python scripts/encrypt_database.py
   ```

   It prompts for the data passphrase (or reads `KALETA_DATA_PASSPHRASE`),
   writes a plaintext pre-encryption backup ZIP to `KALETA_BACKUP_DIR`,
   re-encrypts every row and blind index, and prints the recovery code
   **once**.
3. **Save the recovery code** somewhere safe — it is not shown again.
4. Start the app with `KALETA_ENCRYPTION=passphrase` set and confirm it
   opens.
5. **Delete the plaintext backup ZIP** from `KALETA_BACKUP_DIR` once the
   app opens correctly.

`scripts/encrypt_database.py --decrypt` reverses the process (needed
before an Alembic downgrade past the encryption migration).

## Public demo

The recommended demo is a **separate, single-tenant instance** with
encryption off: one published login, no passphrase step, and nothing about
it complicates the privacy statement of the real instance.

```env
KALETA_DEMO=true                 # the dismissible demo banner
KALETA_DB_URL=postgresql+asyncpg://...   # its own database (or SQLite)
KALETA_SECRET_KEY=...
KALETA_BACKUP_ENABLED=false
```

Seed it once and every night (03:00 UTC here):

```bash
uv run python scripts/reset_demo.py
```

```cron
0 3 * * * cd /opt/kaleta && KALETA_DEMO=true KALETA_DB_URL='...' KALETA_SECRET_KEY='...' /usr/local/bin/uv run python scripts/reset_demo.py >> /var/log/kaleta-demo-reset.log 2>&1
```

| Field | Value |
|---|---|
| Username | `demo` |
| Password | `demo-kaleta` |
| Data passphrase (only with `KALETA_ENCRYPTION=passphrase`) | `demo-kaleta-data` |

**The demo as an account of the hosted instance** works too:
`reset_demo.py --tenant demo` (with `KALETA_DEMO=true` on that instance)
signs in `demo@kaleta.app` (`--email`) at the provider, provisions its account
on the first run, sets up the published passphrase and reseeds it in place
every night. With Supabase the identity must exist and be confirmed first —
add it once in *Authentication → Users* with "Auto confirm". The demo's
password and passphrase are public, so anyone can read that one account;
every other account stays as private as before.

The script refuses to run unless `KALETA_DEMO=true` (`--force` for local
testing), and refuses `--tenant` on a single-tenant install.

## Related

- CI Postgres matrix: `.github/workflows/ci.yml` (`postgres` job, including the tenant-isolation suites)
- CI Valkey mode (sessions + rate limiter): `.github/workflows/ci.yml` (`valkey` job, `valkey/valkey:8`)
- Plan: [`q4-supabase-deployment`](plans/archive/q4-supabase-deployment.md)
- What the operator stores and sees: [`docs/privacy.md`](privacy.md)
