---
plan_id: self-host-guide
title: Self-hosting guide — one machine, HTTPS for the PWA, backups you own
area: docs / ops
effort: small
status: archived
archived_at: 2026-10-11
roadmap_ref: ../../roadmap.md#2027-directions
---

# Self-hosting guide — one machine, HTTPS for the PWA, backups you own

## Intent

After [`postgres-only`](postgres-only.md) a family runs Kaleta on its own
machine with one compose file. ADR-38 hands backups to whoever runs the
database, so the documentation must make that easy to do right: from an
empty homelab to an installed PWA on the phone, a nightly `pg_dump`, a
restore that has been tried once, and upgrades. Published on the
documentation site (GitHub Pages, `mkdocs.yml`).

## Scope

- `docs/self-hosting.md` (in the MkDocs nav):
  - Requirements (CPU/RAM measured on the compose stack, disk per year of
    a typical ledger), Podman or Docker.
  - Install: `docker-compose.yml`, the `.env` it needs (generated
    `KALETA_SECRET_KEY` and database password), first run (admin + first
    family), what the data passphrase and recovery code are and why
    losing both loses the data. **Finish the first run (or run
    `tenant_admin.py create-login --admin`) before the instance is
    reachable from outside**: the first sign-up of an empty instance becomes
    its administrator.
  - HTTPS, needed for the PWA: (a) Cloudflare Tunnel with `cloudflared`
    as a compose service — no open ports; (b) Caddy reverse proxy with an
    automatic certificate. One worked example each.
  - Backups: a `backup` compose service (or a host cron) running
    `pg_dump -Fc` nightly into a mounted directory with retention; why a
    copy must leave the machine; what a dump contains (ciphertext of
    user-written text, plaintext amounts — ADR-35); the restore
    procedure, and a restore drill to run once.
  - Upgrades: pull, `up -d`, migrations run at start; how to roll back
    (restore the dump taken before).
  - Families: creating them, registration modes, the member limit.
- `deploy/selfhost/` with the optional compose overlays the guide uses
  (`cloudflared`, `backup`), validated by `compose config` in CI.

### Not in scope

- The hosted instance's runbook (`docs/deployment.md`).
- Automated off-site backup targets (S3/R2 clients) beyond one example.

## Acceptance criteria

- `grep -q "self-hosting.md" mkdocs.yml`
- `podman compose -f docker-compose.yml -f deploy/selfhost/backup.yml config`
- `podman compose -f docker-compose.yml -f deploy/selfhost/cloudflared.yml config`
- `uv run python scripts/check_doc_links.py`
- `uv run mkdocs build --strict --site-dir /tmp/kaleta-site`
- `[manual]` Follow the guide on a clean machine; take a dump, drop the volume, restore, sign in, data passphrase opens the family.

## Touchpoints

`docs/self-hosting.md` (new), `mkdocs.yml`, `deploy/selfhost/*.yml`
(new), `README.md` (link), `.github/workflows/ci.yml` (compose config).

## Open questions

- Encrypt the dump at rest (`age`)? Default: documented as optional; the
  user-written text is already ciphertext.

## Implementation notes

- **No `.env` with secrets.** Since `postgres-only` C2 the compose file
  generates the database password and `KALETA_SECRET_KEY` itself (the
  `kaleta-secrets` volume). The guide says so. `.env` holds only what the
  HTTPS overlays need (tunnel token, public URL or domain) and, optionally,
  `COMPOSE_FILE`.
- **Measured, not guessed (2026-10-11, Podman 6.1 on arm64, PostgreSQL 18.6).**
  With six years of example data (`scripts/seed.py`: 1,584 transactions,
  576 budgets), Kaleta idled at about 150 MB and peaked at about 320 MB while
  drawing the dashboard, the forecast and the reports. PostgreSQL used about
  60 MB. The database was 11 MB empty and 13.2 MB seeded; the family's schema
  was 3.2 MB, of which the audit log was 1.2 MB. That is about 2 kB per
  transaction. The `-Fc` dump was 1.2 MB. CPU stayed in single digits, which
  `podman stats` samples too coarsely to give a peak worth printing, so the
  guide says "one or two cores".
- **The `[manual]` criterion, run on this machine.** `backup` overlay up;
  `kaleta-backup` wrote the dump; `kaleta` and `backup` stopped; `db` removed;
  `kaleta_kaleta-pg` dropped; `up -d --wait db`; `pg_restore --no-owner`;
  `up -d --wait kaleta`. The same family schema and 1,584 transactions came
  back. A browser signed in, unlocked with the data passphrase and showed
  decrypted payees. The first attempt, without `--wait`, ran `pg_restore`
  against a server that was not up yet: nothing was restored and Kaleta
  started on an empty database. The guide's restore uses `--wait` and says
  why.
- **`KALETA_SECRET_KEY` is part of a backup.** Only the TOTP secrets
  (`user_mfa.totp_secret`, `EncryptedString`) are sealed under it. The guide
  says to keep a copy next to the recovery code, and what to do without it
  (`reset-password --disable-mfa`).
- **Three overlays, not two.** `deploy/selfhost/caddy.yml` sits beside
  `cloudflared.yml` and `backup.yml`, so the Caddy example is a file CI
  validates and not a snippet in prose. Each HTTPS overlay re-binds 8080 to
  loopback with `ports: !override` (Compose 2.24+). The CI `compose` job runs
  `config` for the base file and every overlay.
- **`mkdocs build --strict` was failing on `main`.** Four links from `docs/`
  pointed at files outside it (`../SECURITY.md` twice, `../docker-compose.yml`
  from C2, `../deploy/postgres/init-app-role.sql`). They now point at GitHub.
  The `pages` workflow runs the same build, so it was broken too.
- **Member limit.** The plan's "the member limit" has nothing behind it yet: a
  family is one login until `hosted-household-sharing`. The guide says that.
- **Review findings (2026-10-11), all taken.**
  - `COMPOSE_FILE` in `.env` is the guide's one way to choose overlays. A
    command typed with fewer `-f` files would rebuild `kaleta` from the base
    file and undo an HTTPS overlay.
  - busybox `crond` runs its jobs with no environment. Run under `env -i`,
    the job failed with `pg_dump: not found`, and `KALETA_BACKUP_KEEP_DAYS`
    was unset. The script now sets `PATH` and the crontab line carries
    `TZ` and the retention. A real `crond` run (the schedule set to every
    minute) wrote the dump and logged it to `podman compose logs backup`.
  - Dumps are `chown`ed to the owner of the backup directory, and the guide
    has it created first. Docker's root-made directory is stated.
  - `kaleta-backup [name]` keeps a pre-upgrade dump apart from the nightly
    one. Stale `*.partial` files are swept.
  - `KALETA_PUBLIC_URL` left the HTTPS overlays: only the Supabase provider
    reads it.
  - The guide asks for Compose 2.24+, because of `!override`.
  - On a reachable machine the guide creates the administrator with
    `kaleta-admin create-login --admin` first.
  - The new-machine key step writes, installs and removes the file; it was
    tried on Podman.
  - The rollback has its order spelled out.
  - Images re-pinned: `cloudflared:2026.10.0`, `caddy:2.11-alpine`.
- **How the measurement seeded around the `taxonomy` bug** (chores.md):
  the fresh family's 8 canonical tags were deleted, and `seed.py` then
  recreated them with everything else.
- **Open question (`age`)**: default taken. It is documented as optional, with
  one command.

## Implementation (filled by plan-archiver)

## Implementation

Landed on 2026-10-11 (PR #207).

| SHA | Author | Date | Message |
|---|---|---|---|
| `c934dba` | Dawid Adamski | 2026-10-11 | Merge pull request #207 from DawidAdamski/docs/self-host-guide |

**Files changed:**
- .github/workflows/ci.yml
- deploy/selfhost/backup.yml
- deploy/selfhost/caddy.yml
- deploy/selfhost/cloudflared.yml
- docs/deployment.md
- docs/getting-started.md
- docs/plans/chores.md
- docs/plans/self-host-guide.md
- docs/privacy.md
- docs/self-hosting.md
- mkdocs.yml
- README.md

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `grep -q "self-hosting.md" mkdocs.yml` | 0 |
| `podman compose -f docker-compose.yml -f deploy/selfhost/backup.yml config` | 0 |
| `podman compose -f docker-compose.yml -f deploy/selfhost/cloudflared.yml config` | 0 |
| `uv run python scripts/check_doc_links.py` | 0 |
| `uv run mkdocs build --strict --site-dir /tmp/kaleta-site` | 0 |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
