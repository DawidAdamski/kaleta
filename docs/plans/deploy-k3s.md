---
plan_id: deploy-k3s
title: Deploy Kaleta on a self-hosted k3s cluster
area: deploy
effort: large
status: in-progress
roadmap_ref: ../roadmap.md
---

# Deploy Kaleta on a self-hosted k3s cluster

## Intent

Run Kaleta on the owner's own k3s cluster: the app, its PostgreSQL, TLS, backups and
upgrades, as a small set of manifests (or a Helm chart) that a homelab operator applies and
forgets. The self-hosted layout is the default (ADR-38: one Postgres, schema per family,
local logins, encryption always on), so this is `KALETA_AUTH_BACKEND=local` with no
Supabase. **Do this plan last**, once the features above are merged.

## What exists (2026-10-12)

- `docs/deployment.md` (hosted, Supabase) and `docs/self-hosting.md` (single container).
- `deploy/selfhost/` has Caddy, Cloudflared and a backup compose file; `deploy/postgres/`
  has the app-role SQL. No Kubernetes manifests yet.
- The image `kaleta:full` ships the registry migrations and migrates on start
  (registry, then each family's schema). `GET /api/v1/health` reports migration and
  keyring state. The `KeyRing` is in-process: a restart sends every member to `/unlock`.

## Scope

- **Manifests / a Helm chart** under `deploy/k3s/` (decide Helm vs plain + kustomize in the
  open question):
  - **PostgreSQL**: a StatefulSet with a PVC (local-path or Longhorn on k3s), the app role
    from `deploy/postgres/init-app-role.sql`, and `KALETA_DB_URL` wired from a Secret. An
    external managed Postgres is also supported by pointing the URL at it and skipping the
    StatefulSet.
  - **App Deployment**: `replicas: 1` by default (the KeyRing and the file-backed sessions
    make one replica the simple, correct case), `KALETA_AUTH_BACKEND=local`,
    `KALETA_SECRET_KEY` and the DB URL from Secrets, a PVC at `~/.kaleta` for sessions, a
    readiness probe on `/api/v1/health` and a liveness probe, resource requests/limits.
  - **Ingress + TLS**: Traefik (k3s's built-in) with cert-manager for Let's Encrypt, or
    the bundled Caddy as an alternative; `KALETA_PUBLIC_URL` and
    `KALETA_SESSION_COOKIE_SECURE=true` set accordingly.
  - **Migrations on deploy**: the app migrates on start, so a rolling update runs them; a
    note on the one-replica `Recreate` strategy so two versions never migrate at once.
    Optionally a `Job` or initContainer that runs `scripts/migrate_tenants.py` and gates
    readiness.
  - **Backups**: a CronJob that `pg_dump`s to a PVC or object storage (restic/rclone),
    reusing the intent of `deploy/selfhost/backup.yml`.
- **A multi-replica note, not the default**: if the operator scales up, they add Valkey
  (`KALETA_REDIS_URL`), sticky sessions on the Ingress, and accept that a restart still
  locks keys — documented, with the manifest knobs, but `replicas: 1` stays the shipped
  value.
- **`docs/deploy-k3s.md`**: apply order, the Secrets to create, scaling, upgrades,
  restore-from-backup, and the "every restart needs re-unlock" behaviour.
- **Smoke test**: a script that applies the manifests to a local k3d/kind cluster, waits
  for `/api/v1/health`, creates the first account and signs in, so the chart is known to
  stand up. CI can run it on kind.

## Not in scope

- Supabase on k3s (the hosted layout is a different deployment; this plan is the
  self-hosted default).
- A public Helm repository or an operator CRD — a chart in the repo is enough for v1.
- High availability of PostgreSQL (one instance with backups; HA Postgres is its own plan).

## Acceptance criteria

- `deploy/k3s/` applies cleanly to a fresh k3d/kind cluster and `/api/v1/health` returns
  `database_ok: true` with no pending migrations.
- The smoke-test script creates an account and signs in against the deployed instance.
- `docs/deploy-k3s.md` covers apply, Secrets, TLS, backup/restore, upgrade and scaling.
- `./scripts/verify.sh` stays green (no app code changes expected; any are called out).

## Touchpoints

`deploy/k3s/*` (new), `deploy/postgres/init-app-role.sql`, `scripts/k3s-smoke.sh` (new),
`docs/deploy-k3s.md` (new), `docs/deployment.md` / `docs/self-hosting.md` (cross-links),
`.github/workflows/*` (optional kind smoke test), `README.md` (a deploy pointer).

## Implementation notes

### Delivery in slices

`large` plan; ships in single-purpose PRs:

- **Slice 1 — the Helm chart + docs (this PR).** A Helm chart under
  `deploy/k3s/` (bundled Postgres StatefulSet, app Deployment, Service, Traefik
  Ingress + cert-manager, Secret, backup CronJob), `values.yaml` with the knobs,
  and `docs/deploy-k3s.md`. Validated statically with `helm lint` and
  `helm template | kubectl apply --dry-run`. No app-code changes.
- **Slice 2 — prove it stands up (later).** `scripts/k3s-smoke.sh` stands up a
  k3d cluster, installs the chart, waits for `/api/v1/health`, creates the first
  account and signs in; optional kind CI job. Live cluster run lives here, not
  in Slice 1.

### Decisions (Slice 1)

- **Helm chart, not kustomize** (open question 1): the knobs (domain, storage
  class, replica count, bundled-vs-external Postgres, image tag) are exactly a
  `values.yaml`. Validated with `helm` 4.x locally.
- **Bundled Postgres StatefulSet, external supported** (open question 2):
  `postgres.enabled=true` ships a single-instance StatefulSet with a PVC and the
  app role from `deploy/postgres/init-app-role.sql` (as a ConfigMap-mounted init
  script); set `postgres.enabled=false` + `externalDatabase.url` to point at a
  managed Postgres.
- **Traefik + cert-manager default** (open question 3): k3s ships Traefik; the
  Ingress carries a `cert-manager.io/cluster-issuer` annotation. Caddy stays
  documented as the alternative (the existing `deploy/selfhost/caddy.yml`).
- **Pinned image tag** (open question 4): `image.tag` defaults to the current
  release (`ghcr.io/dawidadamski/kaleta`, published by `.github/workflows/docker.yml`),
  never `latest`; a rollout is a deliberate tag bump.
- **One replica, `Recreate`** : the in-process KeyRing and file-backed sessions
  make `replicas: 1` the correct default; the Deployment uses `strategy:
  Recreate` so two versions never migrate at once. Multi-replica (Valkey +
  sticky sessions) is a documented, non-default knob.

## Open questions

- Helm chart or plain manifests + kustomize? Default: a Helm chart — values for the
  domain, storage class, replica count and external-vs-bundled Postgres are exactly what a
  chart's `values.yaml` is for; kustomize overlays are the fallback if we want no Helm
  dependency.
- Bundled PostgreSQL StatefulSet or require an external one? Default: bundle one (a homelab
  rarely has managed Postgres) and support pointing at an external URL.
- Traefik + cert-manager, or the bundled Caddy as a sidecar/edge? Default: Traefik +
  cert-manager (k3s ships Traefik), Caddy documented as the alternative.
- Image tag strategy for upgrades? Default: pinned version tags (never `latest` in the
  manifest), so a rollout is a deliberate tag bump and a rollback is the previous tag.
