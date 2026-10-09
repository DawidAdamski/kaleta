---
adr_id: "038"
title: "PostgreSQL Only, One Tenancy Layout for Self-Hosted and Hosted"
status: accepted
---

# ADR-38: PostgreSQL Only — One Tenancy Layout for Self-Hosted and Hosted

- **Context**: Kaleta runs two layouts today. Self-hosted installs use
  `KALETA_TENANCY=single` on SQLite (or Postgres), local argon2 logins,
  encryption off, app-managed SQLite backups and an optional desktop window
  (`KALETA_MODE=app`). The hosted instance uses `multi`
  ([ADR-35](035-hosted-multi-tenancy-and-user-held-encryption.md)): a
  `public` registry, one Postgres schema per account, Supabase Auth and
  field encryption under a key the members hold. Every feature is built and
  tested twice: two dialects (`sql_compat`, `render_as_batch`,
  `native_enum=False`), two tenancy paths, and a CI matrix that runs the whole
  unit + integration suite once on SQLite and once on Postgres (≈ 3.5 and
  5.5 minutes on 2026-10-09).
  The product direction is now one web application with two ways to get it:
  **host it yourself** on one machine (a homelab, a VPS) or **use the
  instance the maintainer hosts**. In both, a *family* is one account with up
  to ten members. A local-first app with encrypted sync (the stronger,
  end-to-end option) was considered and set aside — see Rejected
  alternatives. Nobody runs a SQLite install worth migrating: the
  maintainer's own data is re-imported from bank exports.
- **Decision**:
  1. **PostgreSQL is the only database** (16 or newer). SQLite support is
     removed: `aiosqlite`, the dialect branches in `kaleta.db.sql_compat`,
     batch-mode migrations for new revisions, and every "keep SQLite
     compatibility" rule. Postgres-only features (native enums, `JSONB`,
     partial indexes, `ON CONFLICT`) become allowed where they help.
     Existing SQLite databases are **not migrated**; they are dropped.
     Supersedes [ADR-2](002-sqlalchemy-20-with-dual-database-support.md).
  2. **One tenancy layout everywhere** — ADR-35's: a `public` registry and
     one schema per family. `KALETA_TENANCY` disappears. A homelab install
     is a one-machine instance that holds one family, or several (a
     grandparent's, a sibling's). The same migrations, encryption and
     isolation tests cover both ways of running Kaleta.
  3. **Field encryption is always on.** Every member has a data passphrase
     and a recovery code; ADR-35's key hierarchy and threat model apply
     unchanged. On a self-hosted instance the operator *is* the family, so
     the "key in server memory while signed in" limit costs nothing; on the
     hosted instance it is stated in [privacy.md](../privacy.md).
     `KALETA_ENCRYPTION=off` survives only for `KALETA_DEBUG=true`.
  4. **Identity has two backends, both multi-tenant.** `local` keeps argon2
     password hashes — moved from each tenant's `users` table to a
     registry table, so one login maps to one family — and needs no e-mail
     provider. `supabase` stays the hosted backend. The `fake` backend is
     retired once `local` covers what it was written for (a hosted-shaped
     stack without Supabase).
  5. **An instance administrator** exists on every instance: the first
     identity created on an empty instance (or one made with
     `tenant_admin.py`). They see families (name, member count, status —
     never financial data), suspend, resume or delete them, and choose how
     families are created: *closed* (admin creates them), *invite-only*,
     or *open sign-up*. Self-hosted defaults to closed; the hosted instance
     runs open sign-up.
  6. **A family has at most ten members** (`KALETA_HOUSEHOLD_MAX_MEMBERS`,
     default 10, previously planned as 4). Roles stay `owner` and `member`.
  7. **No desktop window.** `KALETA_MODE=app` is removed; installing Kaleta
     on a phone or computer is the PWA of
     [ADR-17](017-progressive-web-app-pwa-support.md), which needs HTTPS (or
     `localhost`) — on a homelab, a reverse proxy with a certificate or a
     Cloudflare Tunnel. `web` and `api` modes stay.
  8. **Backups belong to whoever runs the database.** The app-managed SQLite
     backups (`KALETA_BACKUP_*`, the scheduler, the safety copy before a
     migration) are removed. Self-hosters get a documented `pg_dump`
     routine (and a restore drill) on the documentation site (GitHub
     Pages, built from `docs/` by MkDocs); the hosted
     instance relies on Supabase backups as documented in
     [deployment.md](../deployment.md). A family's own export stays in
     Settings → Data as the user-level copy.
  9. **Tests run against PostgreSQL only**, in a local container and in
     parallel (one database per worker). The laptop runs the whole suite
     (`verify.sh`, pre-push); CI stays the merge gate but runs only the
     fast tier per pull request, the slow tier on `main` and nightly. The
     SQLite CI job is removed.
- **Rejected alternatives**:
  - *Keep SQLite for self-hosters.* The cheapest install (one container, no
    database server) — paid for with two dialects, two tenancy paths and a
    doubled CI matrix on every change. Running Postgres beside Kaleta in one
    compose file is a small cost to a self-hoster.
  - *Keep `single` tenancy on Postgres for self-hosters.* Removes the
    dialect problem but keeps two code paths for routing, auth, encryption
    and migrations, and a self-hosted family would test none of the
    isolation the hosted one relies on.
  - *Local-first app with end-to-end encrypted sync* (the model of Actual
    Budget or Obsidian Sync): keys never leave the device, the server holds
    ciphertext only. The strongest privacy option, but it needs a sync
    protocol and conflict resolution between devices, ships an installer
    instead of a link, and the multi-device household becomes a
    distributed-systems problem. Self-hosting gives a family the same
    "nobody else can read it" outcome on today's architecture. Kept on
    record if hosted users ask for end-to-end encryption.
  - *A browser-side app (static hosting, encryption in JavaScript).* A
    rewrite of the UI and of every server-side computation (budgets,
    Prophet forecasts), and the server still ships the JavaScript that
    sees the passphrase.
- **Consequences**:
  - A self-hosted install is two containers (Kaleta and Postgres) in one
    compose file. Development and tests need a local Postgres
    (`podman`/`docker`); `uv run pytest` without one fails with a sentence
    saying how to start it.
  - Forgetting both the data passphrase and the recovery code now loses
    data on a self-hosted instance too, unless another family member can
    re-approve. First sign-in already forces the recovery code to be
    saved; the self-hosting guide repeats it next to the backup routine.
  - Rules and docs that assume SQLite change in the same plan that removes
    it: `AGENTS.md` ("Keep SQLite compatibility"), `docs/tech-stack.md`,
    `docs/getting-started.md`, `docs/deploy-local.md`, the default
    `KALETA_DB_URL`, `Containerfile` and `docker-compose.yml`.
  - ADR-35's last consequence ("self-hosted installs run `single` …") no
    longer holds; its other decisions stand.
- **Plans**: [`test-suite-speed`](../plans/archive/test-suite-speed.md),
  [`postgres-only`](../plans/postgres-only.md),
  [`instance-admin-panel`](../plans/instance-admin-panel.md),
  [`hosted-household-sharing`](../plans/hosted-household-sharing.md),
  [`self-host-guide`](../plans/self-host-guide.md).
