---
plan_id: container-nonroot-hardening
title: Run the container images as a non-root user (F-6)
area: security (deploy/containers)
effort: small
status: archived
archived_at: 2026-10-20
roadmap_ref: ../../roadmap.md
---

# Run the container images as a non-root user (F-6)

## Intent

The Trivy `config` scan (`security-trivy-scan`, finding **F-6**, DS-0002, High)
reported that neither `Containerfile` nor `Containerfile.full` declares a
non-root `USER`, so the application runs as `root` inside the container. A
container escape then starts with root. Best practice — and the fix here — is a
dedicated non-root runtime user, with a `runAsNonRoot` securityContext in the
k3s Deployment as defence-in-depth.

## Scope

- **`Containerfile` + `Containerfile.full`** — create a dedicated non-root user
  (fixed uid 10001), hand it ownership of `/app` (the code + the `.venv` built
  as root), set an explicit `HOME`, and `USER` down to it before `CMD`.
- **`deploy/k3s/templates/deployment.yaml`** — the file-backed NiceGUI sessions
  volume is mounted at `/root/.kaleta` *because the image ran as root*. Move it
  to the new user's `HOME/.kaleta`, update the comment, and add
  `runAsNonRoot: true` + `runAsUser` / `runAsGroup` / `fsGroup` to the pod
  `securityContext` (which already sets `seccompProfile: RuntimeDefault`; the
  container already drops all caps and forbids privilege escalation).
- **Regression guard** — `KAL-SEC-005` + an integration test asserting both
  Containerfiles declare a non-root `USER` and the Deployment pins
  `runAsNonRoot`. Fails on today's images, passes after the fix.

## Not in scope

- A distroless/slimmer base image (that is F-7's tracked mitigation, a separate
  later step).
- The bundled Postgres / Valkey manifests — only the app Deployment.
- Read-only root filesystem (`readOnlyRootFilesystem`) — a further hardening
  step once the writable paths (`.venv`, `HOME`, `/tmp`) are confirmed; noted
  for a follow-up rather than done blind here.

## Acceptance criteria

- `Containerfile` and `Containerfile.full` each declare a non-root `USER` and
  own `/app` as that user; the image still starts (`CMD` unchanged).
- `deploy/k3s/templates/deployment.yaml` mounts sessions under the runtime
  user's `HOME`, and the pod `securityContext` sets `runAsNonRoot: true`.
- `uv run python scripts/security/scan_trivy.sh config` no longer reports
  DS-0002 for either Containerfile (verified by a real build + scan).
- `KAL-SEC-005` is `@automated` and its covering test (`Covers: KAL-SEC-005`)
  lives in `tests/integration/`; `scripts/spec_coverage.py` stays green.
- `./scripts/verify.sh` passes (no `src/` change → short gate).

## Touchpoints

`Containerfile`, `Containerfile.full`,
`deploy/k3s/templates/deployment.yaml`, `docker-compose.yml`,
`compose.hosted-dev.yml`, `docs/deployment.md`, `docs/bdd.md` (KAL-SEC-005),
`tests/integration/test_container_hardening.py` (new).

The F-6 row in `docs/security/assessment-2026-10-12.md` is introduced by the
`security-trivy-scan` PR (#308), not yet on `main`. Flipping it to **Fixed**
is deferred to after #308 merges: this branch rebases onto the new `main` and
the one-line status flip rides along before this PR merges. Editing the
assessment here would touch a version of the file that has no F-6 row yet.

## Implementation notes

- uid/gid **10001**, user `app`, `HOME=/home/app`; sessions move from
  `/root/.kaleta` to `/home/app/.kaleta`.
- The `.venv` is built by `uv sync` as root; `chown -R app:app /app /home/app`
  after the final sync hands it over, and `UV_NO_SYNC=1` keeps the runtime from
  writing to it. `fsGroup` makes the mounted sessions volume group-writable by
  the runtime user (k3s).
- **Compose has no `fsGroup`.** `docker-compose.yml` and `compose.hosted-dev.yml`
  (both build `kaleta:full`) mounted the sessions named volume at
  `/root/.kaleta`; repointed to `/home/app/.kaleta`. So a *fresh* named volume
  initialises app-owned, the image pre-creates `/home/app/.kaleta` owned by
  `app` — Docker copies that ownership into an empty named volume on first
  mount. Verified: a container run as uid 10001 can write the mounted path.
- **Existing volumes (migration).** A volume that already holds root-owned
  session files at the old path will not auto-migrate: the data sat at
  `/root/.kaleta`, which is no longer mounted, and the new path's files are
  root-owned from the prior run. Operators either start fresh (sessions are
  disposable — everyone re-unlocks, which a restart already forces) or
  `chown -R 10001:10001` the volume once. Noted here rather than scripted,
  since sessions are ephemeral by design.
- `docs/deployment.md` updated (`/root/.kaleta` → `/home/app/.kaleta`).

## Implementation

Landed on 2026-10-20 (PR #309).

| SHA | Author | Date | Message |
|---|---|---|---|
| `8e3d6ce` | Dawid Adamski | 2026-10-20 | Merge pull request #309 from DawidAdamski/feat/container-nonroot-hardening |
| `c5e3809` | Dawid (Ani) | 2026-10-20 | feat(deploy): run the container images as a non-root user (F-6) |

**Files changed:**
- compose.hosted-dev.yml
- Containerfile
- Containerfile.full
- deploy/k3s/templates/deployment.yaml
- docker-compose.yml
- docs/bdd.md
- docs/deployment.md
- docs/plans/container-nonroot-hardening.md
- tests/integration/test_container_hardening.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Touchpoints verified manually against `c5e3809` (all listed files changed). Plan not listed in the `docs/plans/README.md` index, so no index row was updated. Acceptance criteria were not re-run (validated by PR CI).
