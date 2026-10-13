<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Deploy Kaleta on k3s (Helm)

A Helm chart under [`deploy/k3s/`](../deploy/k3s/) runs Kaleta on a self-hosted
k3s (or any Kubernetes) cluster: the app, a bundled PostgreSQL, TLS via Traefik
+ cert-manager, and a `pg_dump` backup CronJob. This is the self-hosted default
(ADR-38): **one Postgres, a schema per family, local logins, field encryption
always on**.

For a single-container / Compose setup see [`self-hosting.md`](self-hosting.md);
for the hosted (Supabase) layout see [`deployment.md`](deployment.md).

## What you get

| Object | When | Notes |
|---|---|---|
| `Deployment` (app) | always | `Recreate` at `replicaCount: 1`; `RollingUpdate` above it — KeyRing is in-process |
| `Service` + `Ingress` | `ingress.enabled` | Traefik class, cert-manager TLS; sticky-cookie annotations when `ingress.stickySessions` |
| `Secret` | unless `secrets.existingSecret` | `KALETA_SECRET_KEY`, `KALETA_DB_URL` (+ Postgres bootstrap creds) |
| `StatefulSet` (Postgres) + headless `Service` + init `ConfigMap` | `postgres.enabled` | single instance, PVC, non-superuser app role |
| `StatefulSet` (Valkey) + headless `Service` | `redis.enabled` | single instance; shared session + rate-limit state, never keys |
| `PodDisruptionBudget` | `replicaCount > 1` & `podDisruptionBudget.enabled` | keep ≥1 app pod through a node drain |
| `CronJob` + `PVC` (backup) | `backup.enabled` & `postgres.enabled` | nightly `pg_dump -Fc`, N-day retention |
| `PVC` (sessions) | `app.persistence.enabled` & `replicaCount == 1` | `~/.kaleta` for NiceGUI sessions (multi-replica keeps sessions in Valkey) |

## Prerequisites

- A cluster with an ingress controller (k3s ships **Traefik**) and, for TLS,
  **cert-manager** with a `ClusterIssuer` (default `letsencrypt-prod`).
- A `StorageClass` (k3s ships **local-path** as the default; leave the
  `storageClass` values empty to use it).
- `helm` 3.8+ (developed against helm 4.x) and `kubectl`.
- A DNS record for `ingress.host` pointing at the cluster's ingress IP.

## The three required values

Everything has a homelab-sane default except:

1. `ingress.host` — the hostname the app is served at.
2. `secrets.secretKey` — signs session cookies; the app **refuses to start** in
   production with the insecure default. Generate one: `openssl rand -hex 32`.
3. The database password — `postgres.appPassword` (bundled) **or** the full
   `externalDatabase.url` (external). The shipped defaults (`kaleta_app`,
   `postgres`) are placeholders — change them.

> The chart `fail`s at render time if `secretKey` is empty, or if
> `postgres.enabled=false` with no `externalDatabase.url` — a misconfigured
> release never reaches the cluster.

> Keep the bundled `postgres.appPassword` to unreserved characters (hex is
> ideal): it goes verbatim into the `KALETA_DB_URL` and into an inline SQL
> string, so a `@`, `:`, `/` would need URL-encoding and a `'` would break the
> init SQL. For an external DB, URL-encode the password in `externalDatabase.url`
> yourself.

## Install — bundled Postgres (default)

```sh
helm install kaleta deploy/k3s \
  --namespace kaleta --create-namespace \
  --set ingress.host=kaleta.example.com \
  --set secrets.secretKey="$(openssl rand -hex 32)" \
  --set postgres.appPassword="$(openssl rand -hex 24)" \
  --set postgres.postgresPassword="$(openssl rand -hex 24)"
```

The bundled Postgres StatefulSet creates the `kaleta` database and a
**non-superuser** app role (`kaleta_app`) via an init script that mirrors
[`deploy/postgres/init-app-role.sql`](../deploy/postgres/init-app-role.sql) (the
hosted instance's bootstrap);
the role owns nothing it does not need — it may create schemas (one per family,
ADR-38) and the registry tables in `public`, nothing more. The init script runs
once, on an empty data directory; the role password is read from the Secret at
runtime, so it is never stored in the ConfigMap.

## Install — external Postgres

Point at a managed instance and skip the StatefulSet (and the bundled backup):

```sh
helm install kaleta deploy/k3s \
  --namespace kaleta --create-namespace \
  --set ingress.host=kaleta.example.com \
  --set secrets.secretKey="$(openssl rand -hex 32)" \
  --set postgres.enabled=false \
  --set backup.enabled=false \
  --set externalDatabase.url='postgresql+asyncpg://kaleta:PASSWORD@db.internal:5432/kaleta'
```

The role on the external server needs `CREATE` on the database and on `public`
(it owns the per-family schemas). See
[`deploy/postgres/init-app-role.sql`](../deploy/postgres/init-app-role.sql) for
the exact grants.

## Secrets & GitOps

The chart renders a Secret from values by default — fine for an imperative
`helm install`, but **plaintext in `values.yaml` does not belong in git**. For a
GitOps flow (Flux/Argo), create the Secret out of band with
[SOPS](https://github.com/getsops/sops) or sealed-secrets and point the chart at
it:

```sh
--set secrets.existingSecret=kaleta
```

The existing Secret must carry `KALETA_SECRET_KEY` and `KALETA_DB_URL` (and, for
the bundled Postgres, `POSTGRES_PASSWORD` + `POSTGRES_APP_PASSWORD`).

## TLS

With `ingress.tls=true` and `ingress.clusterIssuer` set, the Ingress carries a
`cert-manager.io/cluster-issuer` annotation and cert-manager provisions the cert
into `<release>-kaleta-tls`. `ingress.cookieSecure=true` (the default) sets
`KALETA_SESSION_COOKIE_SECURE` so cookies are only sent over HTTPS — **do not
enable it on plain HTTP**, logins would break. This knob is independent of
`ingress.enabled`: if you turn the ingress off and reach the app over plain HTTP
(e.g. a port-forward), set `--set ingress.cookieSecure=false`. An internal CA
(not Let's Encrypt) is just a different `clusterIssuer` name.

## Verify

```sh
kubectl -n kaleta rollout status deploy/kaleta-kaleta
# 503 = database not reachable; database_ok:true + no pending migrations = OK:
kubectl -n kaleta exec deploy/kaleta-kaleta -- \
  python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/api/v1/health').read().decode())"
```

Then open `https://<ingress.host>`, create the first local account and sign in.

> **Every pod restart needs a fresh `/unlock`.** The KeyRing holds the field
> encryption key in memory (ADR-35/38); a restart sends every family back to the
> unlock screen. This is expected for self-hosted, not a fault — and it is why
> persisting sessions buys little and `replicas: 1` is the correct default.

## Backups & restore

With the bundled Postgres, a nightly CronJob runs `pg_dump -Fc` to a PVC
(`backup.retentionDays`, default 14). The dump holds the **ciphertext** of
user-written fields (ADR-35), so a restore is only readable with the **same
`KALETA_SECRET_KEY`** — back up the Secret too (e.g. export it with SOPS and
keep it off-cluster).

Restore needs the dump, which lives on the backup PVC (not mounted in the
Postgres pod). Scale the app to 0 first, then run a one-off pod that mounts the
PVC and restores over the network to the Postgres service:

```sh
kubectl -n kaleta scale deploy/kaleta-kaleta --replicas=0

kubectl -n kaleta run pg-restore --rm -it --restart=Never \
  --image=docker.io/library/postgres:18 \
  --overrides='{"spec":{"containers":[{"name":"pg-restore",
    "image":"docker.io/library/postgres:18","stdin":true,"tty":true,
    "command":["sh","-c","pg_restore -h kaleta-kaleta-postgres -U kaleta_app -d kaleta --clean --if-exists /backup/$DUMP"],
    "env":[{"name":"PGPASSWORD","valueFrom":{"secretKeyRef":{"name":"kaleta","key":"POSTGRES_APP_PASSWORD"}}},
           {"name":"DUMP","value":"kaleta-YYYYMMDD-HHMM.dump"}],
    "volumeMounts":[{"name":"backup","mountPath":"/backup"}]}],
    "volumes":[{"name":"backup","persistentVolumeClaim":{"claimName":"kaleta-kaleta-backup"}}]}}'

kubectl -n kaleta scale deploy/kaleta-kaleta --replicas=1
```

(The backup PVC is `ReadWriteOnce`, so the restore pod must land on the node
holding it; with one node that is automatic. Replace the release prefix
`kaleta-kaleta` and `DUMP` as needed.)

External Postgres: use your provider's backups (`backup.enabled=false`).

## Upgrade

`image.tag` is a pinned version (never `latest`), so a rollout is a deliberate
bump:

```sh
helm upgrade kaleta deploy/k3s --reset-then-reuse-values --set image.tag=0.4.0
```

(`--reset-then-reuse-values` keeps your overrides but still picks up new chart
defaults — safer than `--reuse-values` after a chart bump.)

The app runs its migrations on start (registry first, then each family's
schema); `Recreate` guarantees the old pod is gone before the new one migrates.
Alembic does not auto-revert, so when rolling the version **down** make sure the
schema is compatible first.

## Scaling beyond one replica (not the default)

One replica is the shipped, correct default. Running more is a supported
**opt-in** for throughput and availability (a pod can die without taking the app
down). It never weakens the security model: the account data key stays in the
memory of the pod where the member unlocked, and is **never** put in Valkey
(see the multi-pod addendum in
[ADR-35](adr/035-hosted-multi-tenancy-and-user-held-encryption.md)).

### What multi-replica needs — and what the chart enforces

Three things, all turned on together:

- **Valkey** holds the shared, non-secret state every pod must agree on
  (NiceGUI's session storage, the login rate-limit counters). Bundle one with
  `redis.enabled=true`, or point `redis.url` at your own.
- **Sticky sessions** (`ingress.stickySessions=true`) keep a browser on the pod
  whose in-process KeyRing holds its unlocked key. The chart renders the Traefik
  cookie-affinity annotations on the Service.
- **A rolling update** (`replicaCount > 1` switches the strategy from `Recreate`
  to `RollingUpdate` automatically), a `PodDisruptionBudget`, and a termination
  grace period, so a planned upgrade drains a pod's members onto their
  replacement instead of dropping them.

The chart **refuses to render** `replicaCount > 1` without both Valkey and
sticky sessions, so you cannot ship a config where a request lands on a pod that
never took the unlock.

```sh
helm upgrade --install kaleta deploy/k3s -n kaleta \
  --set replicaCount=3 \
  --set redis.enabled=true \
  --set ingress.stickySessions=true \
  # ... your existing --set flags (host, secrets, …)
# External Valkey instead of the bundled one: drop redis.enabled and use
#   --set redis.url=redis://valkey.my-ns.svc.cluster.local:6379/0
```

### What a member sees on a pod change

- **Rolling upgrade**: sticky affinity + surge-before-drain move most members
  onto the new pod without interruption; the few mid-request get re-balanced.
- **Hard pod loss (crash, scale-in, node drain)**: the affected member stays
  **signed in** (the session lives in Valkey) and is asked only for their **data
  passphrase** again at `/unlock` — never a full re-login, never a silent
  wrong-decrypt. This is exactly today's single-pod restart behaviour, just
  scoped to the members who were on the lost pod.

### Migrations under multiple replicas

No pre-migration `Job` is needed. The startup migration is serialised by a
Postgres **advisory lock**: pods coming up together migrate one at a time, and
the rest find the schema already current and change nothing. App pods do not
serve traffic until `/api/v1/health` reports the schema current (the readiness
probe). **Caveat:** the advisory lock is session-scoped, so `KALETA_DB_URL` must
be a **direct or session-mode** Postgres endpoint — a transaction-pooling
PgBouncer/Supabase pooler would silently defeat it.

### Postgres connection ceiling

Each app pod keeps its own async pool, so N pods multiply connections into the
single Postgres. For a homelab handful of pods this is fine; size
`postgres` accordingly, and reach for PgBouncer (session mode — see the caveat
above) only if you approach the server's `max_connections`.

## Troubleshooting

- **Pod stuck `0/1` not ready** — `/api/v1/health` is 503: the database is not
  reachable or migrations are pending. Check the DB URL and the Postgres pod.
- **App `CrashLoopBackOff` on first start** — usually `secrets.secretKey` left
  at the insecure default (production refuses it) or an unreachable DB URL.
- **cert never issued** — check the `ClusterIssuer` name and that cert-manager
  can solve the challenge for `ingress.host`.
- **Postgres role password changed in values but login still fails** — the init
  script runs only on an *empty* data dir. Changing `postgres.appPassword` after
  the first start does not re-run it; `ALTER ROLE kaleta_app PASSWORD …` by hand
  (and update the Secret) or recreate the PVC.
