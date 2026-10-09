---
plan_id: self-host-guide
title: Self-hosting guide — one machine, HTTPS for the PWA, backups you own
area: docs / ops
effort: small
status: draft
roadmap_ref: ../roadmap.md#2027-directions
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

## Implementation (filled by plan-archiver)
