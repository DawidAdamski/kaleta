---
plan_id: horizontal-scaling
title: Horizontal scaling — more than one replica, with sticky sessions
area: deploy
effort: large
status: in-progress
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
the login rate-limit counters) moves to **Valkey** so every pod agrees on it.

> **Terminology.** The datastore is **Valkey** (the Redis-wire-compatible fork
> we run). The code keeps its existing names because they speak the Redis
> protocol: the `redis-py` client, the `KALETA_REDIS_URL` setting, and
> `RedisStore`. "Valkey" in this plan == whatever `KALETA_REDIS_URL` points at.

> **Not operator-blind to lose.** Nothing secret goes into Valkey in Posture 1 —
> only the authenticated session envelope and rate-limit counters. The account
> **DEK never leaves pod memory** (see the key decision below).

## Why this is not just "set replicas: 3"
Three things break under naïve multi-replica; this plan is really about these:

1. **In-process `KeyRing`** (`src/kaleta/crypto/keyring.py` — *"Unlocked keys, in
   this process's memory only… a restart, or a second replica that did not
   [unlock]"*). A second pod starts with an **empty** key ring, so without
   affinity a request routed there sees "locked" even though the user unlocked
   elsewhere. We do **not** fix this by putting keys in Valkey (that would void
   ADR-35's core property). We fix it with **sticky sessions** + accept re-unlock
   on failover.
2. **NiceGUI is stateful over websockets** and keeps per-client UI state
   server-side; `app.storage` is file-backed by default. Multi-replica needs
   (a) `app.storage` backed by **Valkey** (already wired: `main.py` passes
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

## The key question: operator-blind vs seamless failover — you cannot have both

ADR-35 is **member-held, operator-blind** encryption: the account DEK is sealed
to each member's keypair, unlocked from a *data passphrase* the operator never
holds, and lives in process memory only — "never written to disk, to
`app.storage.user`, or to logs". That is the product's distinguishing promise.

There is a hard theorem here: **if any pod can serve a member without that
member re-providing their secret, then the infrastructure (hence the operator)
can reconstruct the DEK.** Seamless failover across pods and operator-blindness
are mutually exclusive. So this plan presents two postures and recommends the
first.

### Posture 1 — stay operator-blind (RECOMMENDED, no ADR change)
Multi-pod via **sticky sessions**; the DEK stays in the pod where the member
unlocked. Losing that pod (crash, scale-in, node drain) means that member
re-enters their **data passphrase** — which is *already* the behaviour on any
restart today (the DEK is gone on restart by design). Multi-pod does not make
this worse; it just adds pods, and spreads different members across them.
Valkey holds only the **non-secret** shared state (the authenticated session,
rate-limit counters), so after a pod change the member is still *logged in* and
only re-enters the passphrase — not a full login. Graceful rollouts (drain +
affinity) make planned updates almost never force a re-unlock. **This is the
"secure + multi-pod" answer and needs no ADR-35 change.** The DEK is never put
in Valkey.

### Posture 2 — seamless failover (needs an ADR-35 downgrade, hosted-tier only)
To avoid any re-unlock on failover, store the DEK wrapped by an **operator
unwrap key** in Valkey with a TTL, and keep that unwrap key in a **KMS** (or pod
env); any pod unwraps the DEK on a miss.

> The **operator unwrap key** is *not* ADR-35's KEK. ADR-35's KEK is derived
> from the member's data passphrase and wraps the member's private key — the
> operator never holds it. The operator unwrap key here is a **cluster/operator
> secret** whose whole purpose is that the infrastructure can reconstruct the
> DEK without the member. That is exactly what makes it a downgrade.

Plaintext DEKs still live only in memory and Valkey holds only ciphertext, but
the **operator now holds (or can call) the unwrap key, so the operator can
decrypt any account with a live session** — ADR-35's operator-blind promise is
downgraded to "encrypted at rest; the provider can access active-session data",
the normal SaaS posture. This is a conscious policy change: it would amend
ADR-35 and `privacy.md`, and should be a paid-tier opt-in, not the default. Not
pursued unless the product explicitly chooses seamless failover over
operator-blindness — see the separate research track
[`encryption-posture-research`](encryption-posture-research.md).

**Recommendation: build Posture 1.** It delivers secure, multi-pod hosting now;
Posture 2 stays documented as the deliberate trade if seamless failover ever
outweighs the operator-blind guarantee.

## Scope
- **Session isolation — the top safety requirement.** The real fear with shared
  session storage + multi-pod is one member's request ever being served with
  another member's session or DEK. This must be made impossible, not merely
  unlikely:
  - Valkey-backed `app.storage.user` is keyed by NiceGUI's per-client storage id
    (an unguessable id in the signed cookie); a request only ever reads its own
    slot. Audit that nothing derives the slot from a shared/guessable value.
  - The `KeyRing` is keyed by **(tenant schema, member)**; a request resolves its
    DEK strictly from *its own* authenticated subject + tenant (the same binding
    ADR-35 uses today), never from "whatever this pod last unlocked". A pod that
    holds several families' DEKs must never cross them — add a regression test
    that two concurrent sessions for different tenants on one pod cannot read
    each other's rows.
  - The reconnect/re-unlock step (below) must re-verify the passphrase against
    the member's own wrapped key; never treat "some DEK is present on this pod"
    as authorisation.
  - Cookie signing (`KALETA_SECRET_KEY`) must be identical on every pod (one
    Secret), so a session cookie is valid everywhere and forgeable nowhere.
- **Shared state in Valkey** — prove, end to end under >1 replica, that:
  - NiceGUI `app.storage.user` is served from Valkey (not per-pod files), so a
    session is visible on any pod it is routed to.
  - the login rate-limit uses `RedisStore` (`auth/login_rate_limit.py` already
    has `MemoryStore` vs `RedisStore`); counters and lock-outs are shared.
  - document whatever else is process-local and must not be (sweep the code for
    module-level mutable state besides the deliberately-kept `KeyRing`).
- **Sticky sessions** — ingress session affinity (Traefik cookie affinity on the
  Service / `traefik.ingress.kubernetes.io/service.sticky.cookie`), a chart knob
  (`ingress.stickySessions`), and the NiceGUI reconnect implication documented.
- **KeyRing stays in-process (Posture 1)** — keys never placed in Valkey. Record
  the multi-replica posture (sticky affinity + re-unlock-on-failover) as a short
  ADR-35 addendum that *confirms* the operator-blind property still holds under
  multi-pod. No key-wrapping code.
- **Re-unlock UX** — when a request lands on a pod whose `KeyRing` lacks the DEK
  (post-failover) but the Valkey-backed session is still authenticated, prompt
  the member for just the **data passphrase** (a lightweight "reconnect" modal),
  not a full re-login. This is what makes Posture 1 pleasant rather than jarring.
- **Graceful rollouts** — `PodDisruptionBudget`, `terminationGracePeriodSeconds`
  + connection draining, and `RollingUpdate` tuned so a planned upgrade drains a
  pod's members onto their replacement (with affinity) instead of dropping them,
  minimising forced re-unlocks.
- **One-shot migrations** — a mechanism so N pods do not migrate concurrently:
  a pre-install/pre-upgrade migration `Job` (reusing `scripts/migrate_tenants.py`)
  that app pods wait on, or an advisory-lock guard inside
  `ensure_multi_tenant_current`. Pick one in Open questions.
- **Chart / manifests** — a real `replicaCount > 1` path: `RollingUpdate` (not
  `Recreate`) with `maxSurge`/`maxUnavailable` tuned for sticky sessions, a
  `PodDisruptionBudget`, the Valkey/Valkey dependency (bundled sub-chart or an
  external `redis.url`), the migration `Job`, and the affinity annotations.
  `replicas: 1` stays the **default**; this is an opt-in path.
- **Docs** — expand `docs/deploy-k3s.md` "Scaling beyond one replica" from a
  paragraph into a real runbook (Valkey, affinity, migrations, the re-unlock
  behaviour, how to roll out safely).

## Not in scope
- **Posture 2 (KEK-wrapped DEK in Valkey + KMS).** The seamless-failover design
  above; deliberately *not* built here because it downgrades ADR-35's
  operator-blind promise. Documented as the explicit alternative, to be its own
  plan + ADR-35/`privacy.md` amendment only if the product chooses it. Plaintext
  keys in Valkey (no wrapping) are rejected outright.
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
- A regression test: two concurrent sessions for **different tenants** served by
  one process each read only their own tenant's rows and DEK — one can never see
  the other's (the session-isolation safety requirement).
- `[manual]` With `replicaCount=2` + Valkey + sticky sessions on k3d: sign in,
  unlock, and confirm the session survives being served across a rolling update
  of the *other* pod; confirm a hard failover of the pinned pod leaves the member
  **still authenticated** (Valkey session) and prompts only for the data
  passphrase (the reconnect modal), never a silent wrong-decrypt, and never a
  DEK read from Valkey.
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
  Valkey paths; sweep for other process-local state; the re-unlock "reconnect"
  prompt (authenticated session but empty `KeyRing`) likely lives near session /
  the unlock view.
- A short **ADR-35 addendum** confirming the multi-pod posture keeps keys
  operator-blind (Posture 1); Posture 2 would instead be a separate ADR amendment.
- `deploy/k3s/` — `values.yaml` (`replicaCount`, `redis`, `ingress.stickySessions`,
  strategy), new `templates/` for a migration `Job`, `PodDisruptionBudget`, and
  the Valkey/Valkey dependency; `templates/deployment.yaml` strategy + affinity.
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
  hatch. Confirm NiceGUI's Valkey storage + our `RedisStore` target the same
  instance/db cleanly (key prefixes).
- **Does NiceGUI 2.x fully support multi-worker/multi-instance** with Valkey
  storage, or are there known gaps (e.g. `ui.refreshable`, per-client slots,
  reconnect across pods)? Validate against the installed version before
  committing the chart path.
- **Postgres connection pooling** under N app pods × async pool size — do we
  need PgBouncer, or is the per-pod pool small enough? Size it in the plan.

## Implementation notes

### Slice 1 — migration gate (advisory lock), cluster-independent
- **Open question resolved — migration gate mechanism: Postgres advisory lock.**
  Chosen over a pre-upgrade Helm-hook `Job` and over leader election, for the
  reasons the plan already leaned toward: it needs no extra Helm object, DB
  creds or ordering plumbing, and it *also* protects the single-replica
  `Recreate` case at no cost. `ensure_multi_tenant_current` now wraps the whole
  run in `_migration_advisory_lock` (`src/kaleta/services/setup_service.py`): a
  session-level `pg_advisory_lock` on a dedicated AUTOCOMMIT connection, held
  for the duration and released in a `finally` (and automatically if the
  connection drops — a replica dying mid-run frees the lock for the next). The
  body (`_migrate_registry_and_tenants`) is unchanged and already idempotent, so
  waiters that acquire the lock after the first replica finishes find the schema
  at head and do nothing. Lock key is a fixed literal (`_MIGRATION_LOCK_KEY`),
  not a hash, so it can never drift between versions. Covered by
  `tests/integration/test_migration_lock.py` (mutual exclusion, release-on-exit,
  release-on-exception, and a two-thread test that the body never runs
  concurrently) → BDD `KAL-TEN-026 @automated`.
- **Pooler caveat (feeds the PgBouncer open question).** A session-level
  advisory lock only works over a direct (or session-mode) connection: behind a
  transaction-pooling PgBouncer / Supabase pooler, lock and unlock can land on
  different backends and the lock silently does nothing. The migration's
  `KALETA_DB_URL` must be a direct endpoint — documented at `_MIGRATION_LOCK_KEY`
  and to be surfaced in `docs/deploy-k3s.md` / `docs/deployment.md` in the
  chart slice.
- **Deferred (follow-up, not needed for correctness):** `SET lock_timeout` or a
  `pg_try_advisory_lock` poll with a "waiting for migration lock" log line, so a
  replica stuck on a hung migration does not stall other pods' startup silently.
- **Rate-limit `RedisStore` acceptance criterion was already satisfied** before
  this plan: `tests/unit/auth/test_login_rate_limit.py` (`TestRedisStore` +
  the store-parametrised cases, with `fakeredis`) and
  `tests/integration/test_login_rate_limit_replicas.py` (`KAL-AUTH-034`) cover
  the shared-counter path. No new test added — that would duplicate.

### Slice 2 — session-isolation regression test, cluster-independent
- **The top safety requirement is now a test.** `TenantContext` and the data
  key both live in `ContextVar`s (`src/kaleta/db/tenant_context.py`,
  `src/kaleta/db/types.py`), so a request already resolves its tenant schema and
  DEK strictly from its own context, never from "whatever this process last
  unlocked". `tests/integration/test_session_isolation_across_families.py`
  proves it holds under actual concurrency on one process: two families,
  unlocked with distinct passphrases (hence distinct DEKs), read concurrently
  via `asyncio.gather` (each coroutine runs in its own copied context) across 25
  interleaved iterations — each read returns only its own family's payees. A
  second test confirms it fails *closed*: reading one family's rows under the
  other family's key raises `EncryptionError` (the AES-GCM tag rejects the wrong
  key), never returning plaintext. This is the regression guard against the
  anti-pattern the plan forbids — stashing the last-unlocked key in process-wide
  state. → BDD `KAL-ENC-011 @automated`.
  - **Faithful to the request path (review nit).** The read sets only the
    per-task `TenantContext` and lets the DEK ride on `TenantContext.key_ring`
    (filled from the process `KeyRing` for *that* member) — it does **not** use
    `use_data_key` (the explicit-key ContextVar), which would win over the
    context and mask a broken resolution. So the decrypting read genuinely goes
    through `current_data_key()`'s context resolution.
  - **Mutation evidence (red→green).** Replacing `current_data_key()` with the
    anti-pattern — return the process `KeyRing`'s last-unlocked entry, ignoring
    the per-request context — turns **both** tests red (the second-unlocked
    family's key is served to everyone, so the other family's rows fail the
    AES-GCM tag); reverting restores green. A naive mutant that re-reads the
    correct context each call does *not* go red, because decryption is
    synchronous and resolves atomically — which is itself why the ContextVar
    design is sound.
  - The wrong-key assertion pins the `InvalidTag` branch with
    `match="Could not decrypt"`, so a locked tenant, unknown format or
    version mismatch cannot pass for the wrong-key case.
- Existing `tests/integration/test_tenant_isolation.py` already covers *row*
  isolation across tenants (schemas, token rejection, fail-closed) but
  sequentially and with `encryption="off"`; this slice adds the concurrency and
  the DEK-crossover dimensions it does not.

### Slice 3 — ADR-35 multi-pod addendum, cluster-independent
Added an `## Addendum (2026-10)` to
`docs/adr/035-hosted-multi-tenancy-and-user-held-encryption.md` recording that
Posture 1 (N replicas + sticky sessions + re-unlock on failover) keeps every
guarantee of ADR-35: the DEK stays in the unlocking pod's memory, Valkey holds
only non-secret session/rate-limit state, failover costs a re-unlock (not
operator access), one process never crosses families' DEKs (`KAL-ENC-011`), and
replicas migrate once (`KAL-TEN-026`). It also states explicitly that Posture 2
is **not** adopted and would be its own amendment, pointing at
`encryption-posture-research.md`. Documentation only; no code, no new scenario.

### Slice 4 — multi-replica chart path + runbook, cluster-independent to build
`deploy/k3s/` now has a real `replicaCount > 1` path:
- **Strategy** switches from `Recreate` (one replica) to `RollingUpdate`
  (`maxSurge`/`maxUnavailable` tunable, default surge-before-drain) above one,
  with `terminationGracePeriodSeconds` for websocket draining.
- **Bundled Valkey** (`redis.enabled`, a single-instance StatefulSet mirroring
  Postgres) or an external `redis.url`; `KALETA_REDIS_URL` resolves from a
  `kaleta.redisUrl` helper. **Open question resolved — Valkey: bundled by
  default-off with an external escape hatch** (mirrors the Postgres decision).
- **Sticky sessions** (`ingress.stickySessions`) render Traefik cookie-affinity
  annotations on the Service.
- **`PodDisruptionBudget`** rendered only above one replica.
- **Guard**: `kaleta.validateScaling` makes the chart `fail` to render
  `replicaCount > 1` without *both* Valkey and sticky sessions — a broken
  "request lands on a pod that never unlocked" config cannot be shipped.
- **No migration Job** — the Slice 1 advisory lock already serialises concurrent
  startup, so the chart needs no pre-upgrade hook; documented in the runbook,
  with the PgBouncer/session-mode caveat and PG connection-ceiling note. **Open
  question resolved — migration gate stays the advisory lock, not a Job.**
- Validated with `helm lint` + `helm template` (single replica → Recreate, no
  Valkey/PDB; multi → RollingUpdate + PDB + bundled Valkey + sticky + sessions
  as emptyDir; both guard failures; external-`redis.url` path).
- `docs/deploy-k3s.md` "Scaling beyond one replica" expanded into a real runbook
  (what it needs, what the chart enforces, what a member sees on a pod change,
  migrations, the PG ceiling).
- **Review nits folded in:** an external `redis.url` (may carry a password) now
  rides in the chart Secret via `secretKeyRef`, never a plain Deployment env var
  (the bundled URL has none, stays inline); the bundled Valkey runs as the
  image's non-root uid 999 with `fsGroup` so `drop: ALL` does not crash-loop it;
  a `NetworkPolicy` (default on, k3s-enforced) limits the auth-less bundled
  Valkey to app pods, with the residual (sessions are bearer state; use an
  external password-protected Valkey for more) documented; the guard also
  `fail`s on `redis.enabled`+`redis.url` together and on sticky sessions with a
  non-Traefik `className`; and the runbook states migrations must be
  backward-compatible (expand/contract) across the `maxUnavailable: 0` rollout
  window.

Remaining open questions for the live-cluster stage: **sticky granularity**
(Traefik per-browser affinity is accepted — documented consequence: two devices
of one family may pin to different pods, each unlocks its own; keys are
per-member anyway) and **NiceGUI 2.x multi-instance** behaviour, which only a
real `replicaCount=2` run on k3d can confirm.

### Slice 5 — re-unlock on failover: already handled, no new code
Investigated before building a "reconnect modal" and found the behaviour
**already exists**, so none was added (building speculative UI would be waste).

The post-failover state is *identical* to the everyday "signed in but locked"
state the app already handles:
- `SESSION_AUTHENTICATED` and the tenant keys live in `app.storage.user`, which
  NiceGUI backs with Valkey when `KALETA_REDIS_URL` is set — so a failover pod
  still sees the session as **authenticated**.
- `is_unlocked()` consults the *in-process* `KeyRing`, which on a fresh pod is
  empty — so the session reads as **locked**.
- `AuthMiddleware` (`src/kaleta/auth/middleware.py`): authenticated + valid
  tenant + not expired/revoked + `not is_unlocked()` ⇒ `unlock_redirect(path)`
  → `/unlock?redirect_to=…`, the **data-passphrase** prompt, never `/login`.

That is exactly the plan's requirement ("prompt for just the data passphrase,
not a full re-login"). The **guard behaviour** is covered by
`tests/unit/auth/test_unlock_guard.py::test_a_locked_page_load_goes_to_unlock`
(`KAL-ENC-003`): an authenticated session with an empty `KeyRing` requesting a
page is redirected to `/unlock`, and unlocking resumes it — a failover pod is
that case. The test uses a dict-backed fake for `app.storage.user`, so it proves
the guard, not the Valkey-backed *sharing* of the session across pods; that half
rests on the `NiceguiStorageService.configure_environment` wiring (and every pod
sharing `KALETA_SECRET_KEY`) and is confirmed only by the `[manual]` k3d run
below. No `src/kaleta/views/` change, hence no new e2e.

When an already-open page's websocket reconnects to a new pod, the expectation
is that NiceGUI's reconnect ends in a page load, which hits the middleware and
the same `/unlock` gate — the `[manual]` k3d run is what confirms that NiceGUI
2.x actually behaves this way across pods. An *in-place* modal that avoids any
reload is optional UX polish, not a correctness or security requirement, and
would be verifiable only on the cluster too. Deferred, not built.

### Still to do (needs a live cluster — `[manual]` only)
All buildable (cluster-independent) work is done; what remains can be checked
only on a live multi-node cluster:
- a `replicaCount=2` k3d run proving the session survives a rolling update, a
  hard failover prompts only for the passphrase (the `/unlock` gate above),
  migrations run exactly once, and killing one pod keeps the app up for members
  on the survivor;
- confirming NiceGUI 2.x multi-instance behaviour with Valkey storage.

Once those `[manual]` checks pass on the cluster, the plan is complete and can be
archived.
