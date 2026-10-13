---
plan_id: horizontal-scaling
title: Horizontal scaling — more than one replica, with sticky sessions
area: deploy
effort: large
status: draft
roadmap_ref: ../roadmap.md#strategic-direction-open-core
---

# Horizontal scaling — more than one replica

## Intent
Today Kaleta ships `replicas: 1` (see `archive/deploy-k3s.md` and
`docs/deploy-k3s.md`): the in-process `KeyRing`, the file-backed NiceGUI
sessions and the on-start migration make one replica the simple, correct case.
This plan makes running **N replicas** a supported, documented option — for
throughput and for availability (a pod can die without taking the app down) —
**without weakening the security model** that unlocked keys never leave a
process's memory.

The load-bearing idea: **sticky sessions**. With client affinity on the
ingress, a given browser (hence a given signed-in member) keeps landing on the
same pod, whose in-process `KeyRing` holds the key that member unlocked. Keys
are still never shared between pods or written anywhere. Scaling out spreads
*different* members/families across pods; a pod restart or a re-balance just
sends the affected members back to `/unlock`, exactly as a single-pod restart
already does (ADR-35/38). The shared, non-secret state (NiceGUI session storage,
the login rate-limit counters) moves to Redis/Valkey so every pod agrees on it.

## Why this is not just "set replicas: 3"
Three things break under naïve multi-replica; this plan is really about these:

1. **In-process `KeyRing`** (`src/kaleta/crypto/keyring.py` — *"Unlocked keys, in
   this process's memory only… a restart, or a second replica that did not
   [unlock]"*). A second pod starts with an **empty** key ring, so without
   affinity a request routed there sees "locked" even though the user unlocked
   elsewhere. We do **not** fix this by putting keys in Redis (that would void
   ADR-35's core property). We fix it with **sticky sessions** + accept re-unlock
   on failover.
2. **NiceGUI is stateful over websockets** and keeps per-client UI state
   server-side; `app.storage` is file-backed by default. Multi-replica needs
   (a) `app.storage` backed by **Redis** (already wired: `main.py` passes
   `settings.redis_url` to `NiceguiStorageService.configure_environment`, and
   `KALETA_REDIS_URL` is a real setting under the `hosted` extra) and
   (b) **sticky sessions** so the socket.io connection and its reconnects keep
   hitting the same pod.
3. **Every pod migrates on start** (`main.py::_preload_database` →
   `ensure_multi_tenant_current`). With one pod + `Recreate` that is safe; with
   several pods coming up together it is **concurrent migrations on one
   database** — a hazard. Multi-replica needs the migration to run **once**
   (a pre-upgrade `Job`/initContainer, or a Postgres advisory lock, or leader
   election) with the app pods gated on "schema current".

## Scope
- **Shared state in Redis/Valkey** — prove, end to end under >1 replica, that:
  - NiceGUI `app.storage.user` is served from Redis (not per-pod files), so a
    session is visible on any pod it is routed to.
  - the login rate-limit uses `RedisStore` (`auth/login_rate_limit.py` already
    has `MemoryStore` vs `RedisStore`); counters and lock-outs are shared.
  - document whatever else is process-local and must not be (sweep the code for
    module-level mutable state besides the deliberately-kept `KeyRing`).
- **Sticky sessions** — ingress session affinity (Traefik cookie affinity on the
  Service / `traefik.ingress.kubernetes.io/service.sticky.cookie`), a chart knob
  (`ingress.stickySessions`), and the NiceGUI reconnect implication documented.
- **KeyRing posture (decision, not code change)** — keep it in-process; record
  the multi-replica security posture and the re-unlock-on-failover UX in an ADR
  addendum (to ADR-35). State explicitly that keys are never placed in Redis.
- **One-shot migrations** — a mechanism so N pods do not migrate concurrently:
  a pre-install/pre-upgrade migration `Job` (reusing `scripts/migrate_tenants.py`)
  that app pods wait on, or an advisory-lock guard inside
  `ensure_multi_tenant_current`. Pick one in Open questions.
- **Chart / manifests** — a real `replicaCount > 1` path: `RollingUpdate` (not
  `Recreate`) with `maxSurge`/`maxUnavailable` tuned for sticky sessions, a
  `PodDisruptionBudget`, the Redis/Valkey dependency (bundled sub-chart or an
  external `redis.url`), the migration `Job`, and the affinity annotations.
  `replicas: 1` stays the **default**; this is an opt-in path.
- **Docs** — expand `docs/deploy-k3s.md` "Scaling beyond one replica" from a
  paragraph into a real runbook (Redis, affinity, migrations, the re-unlock
  behaviour, how to roll out safely).

## Not in scope
- **Sharing unlocked keys across pods / a KMS/HSM-backed KeyRing.** That is the
  only way to avoid re-unlock on failover, but it changes ADR-35's security
  model fundamentally; it is a separate, larger plan (and an explicit
  non-goal for the self-hosted default). Noted as the alternative.
- **HA PostgreSQL.** One instance with backups stays; HA Postgres is its own
  plan (`deploy-k3s` Not-in-scope already says so). Multi-replica app against a
  single Postgres is fine until the connection ceiling — note pool sizing.
- **Autoscaling (HPA) policy tuning** — the chart should not block it, but
  tuning CPU/RAM targets (Prophet is the spiky, CPU-heavy part) is follow-up.
- **Hosted (Supabase) auth layout** — orthogonal; this plan is the self-hosted
  `local` backend scaling out.

## Acceptance criteria
Most of this needs a live multi-node cluster, so several checks are `[manual]`.

- `uv run pytest tests/unit/auth/ -k rate_limit -q` (RedisStore path covered,
  with `fakeredis`)
- `[manual]` With `replicaCount=2` + Redis + sticky sessions on k3d: sign in,
  unlock, and confirm the session survives being served across a rolling update
  of the *other* pod; confirm a hard failover of the pinned pod sends that
  member to `/unlock` (and nothing is silently decrypted wrong).
- `[manual]` A chart upgrade with `replicaCount=2` runs migrations exactly once
  (the migration Job/lock), and no app pod serves traffic before the schema is
  current.
- `[manual]` Kill one of two pods under light load; the app stays available for
  members pinned to the surviving pod.
- `./scripts/verify.sh` stays green (any app-code change — e.g. the migration
  guard — called out and tested).

## Touchpoints
- `src/kaleta/main.py` (`_preload_database` — migration gate), possibly
  `src/kaleta/services/setup_service.py` (`ensure_multi_tenant_current` advisory
  lock) and `scripts/migrate_tenants.py` (used by a Job).
- `src/kaleta/services/nicegui_storage_service.py`,
  `src/kaleta/auth/login_rate_limit.py`, `src/kaleta/auth/session.py` — confirm
  Redis paths; sweep for other process-local state.
- `deploy/k3s/` — `values.yaml` (`replicaCount`, `redis`, `ingress.stickySessions`,
  strategy), new `templates/` for a migration `Job`, `PodDisruptionBudget`, and
  the Redis/Valkey dependency; `templates/deployment.yaml` strategy + affinity.
- `docs/deploy-k3s.md` (Scaling runbook) and a new ADR addendum to `035-*`.

## Open questions
- **Migration gate mechanism**: pre-upgrade Helm hook `Job` (clean, Helm-native,
  but needs the app image + DB creds and ordering), vs a Postgres **advisory
  lock** inside `ensure_multi_tenant_current` (simpler, no extra object, each pod
  tries but only one migrates while others wait), vs leader election (overkill).
  Leaning: advisory lock — it also protects the single-replica `Recreate` case
  and needs no Helm-hook plumbing.
- **Sticky mechanism**: Traefik cookie affinity is per-browser, so two members
  of one family on different devices can pin to different pods (each unlocks on
  its pod — acceptable, keys per-member anyway). Is per-client affinity enough,
  or do we want family-affinity (not expressible at the ingress)? Likely
  per-client is fine; document the consequence.
- **Valkey: bundled or external?** Mirror the Postgres decision — bundle a small
  Valkey by default (`redis.enabled=true`) with an external `redis.url` escape
  hatch. Confirm NiceGUI's Redis storage + our `RedisStore` target the same
  instance/db cleanly (key prefixes).
- **Does NiceGUI 2.x fully support multi-worker/multi-instance** with Redis
  storage, or are there known gaps (e.g. `ui.refreshable`, per-client slots,
  reconnect across pods)? Validate against the installed version before
  committing the chart path.
- **Postgres connection pooling** under N app pods × async pool size — do we
  need PgBouncer, or is the per-pod pool small enough? Size it in the plan.

## Implementation notes
(filled as work progresses)
