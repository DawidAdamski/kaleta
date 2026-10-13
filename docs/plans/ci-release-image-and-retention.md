---
plan_id: ci-release-image-and-retention
title: Release image dispatch resilience + registry tag retention
area: ci
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Release image dispatch resilience + registry tag retention

## Intent
Two CI gaps around the Docker image, both found while preparing the k3s
deploy:

1. **No semver image tag for releases.** release-please cuts the `vX.Y.Z`
   tag and then dispatches `docker.yml` to build the release image (a tag
   pushed with `GITHUB_TOKEN` cannot trigger `docker.yml`'s `tags: v*`
   path — GitHub's loop guard). But for `0.3.0` the release-please **step
   itself failed** after creating the release — `release-please failed:
   Unable to create comment because issue is locked` — and because the
   dispatch step guards on plain `if: steps.release.outputs.release_created`
   (implicit `success()`), the step was skipped. Result: neither GHCR nor
   Docker Hub got a `0.3.0` / `0.3` tag, only `main` + `sha-<short>`.
   (All recent merged PRs are `locked=true`, so this would recur on every
   release.)

2. **Registry tags accumulate forever.** Every push to `main` adds a
   `sha-<short>` tag on both registries; Docker Hub's free tier has no
   retention policy, so old throwaway `sha-*` tags pile up (262+ on
   `…/kaleta`). We only ever deploy `main`, a semver tag, or a recent sha.

## Scope
Covers:
- Make the release-image dispatch survive a failed/locked-comment
  release-please step (`.github/workflows/release-please.yml`).
- A scheduled + manually-dispatchable retention workflow
  (`.github/workflows/image-retention.yml`) that prunes old `sha-*` tags
  on Docker Hub (keep newest N). Conservative keep-rule: it only ever
  removes `sha-*` tags beyond the newest N — `main`, semver and anything
  else are protected by construction. Manual runs default to **dry-run**
  (list only).

Does NOT cover:
- The root cause of PRs being locked (a repo setting / external actor, not
  a workflow in this repo). Noted below; the dispatch fix makes the image
  build independent of it either way.
- The one-off build of the already-missing `0.3.0` image — that is a
  manual `gh workflow run docker.yml --ref v0.3.0` the maintainer triggers
  (publishes a public image; out of band from this PR).
- **GHCR pruning — deliberately deferred.** `docker.yml` builds with
  provenance attestations, so each tagged image is an OCI *index* whose
  child manifests (image + attestation) appear on GHCR as *untagged*
  package versions. `actions/delete-package-versions`' "delete only
  untagged" mode would delete those children and leave the tagged index
  pointing at missing blobs — pulls of `:main` / `:sha-*` would then fail.
  A safe GHCR prune needs a provenance-aware tool (e.g.
  `snok/container-retention-policy`); out of scope here, where the ask was
  Docker Hub. GHCR is free, generous, and tied to the public repo anyway.
- The `anihilat` Docker Hub namespace: never hard-coded; the workflow
  reads `${{ secrets.DOCKER_USERNAME }}` so nothing personal lands in this
  repo.

## Acceptance criteria
- `test -f .github/workflows/image-retention.yml`
- `grep -q "always()" .github/workflows/release-please.yml`
- `grep -q "release_created == 'true'" .github/workflows/release-please.yml`
- `grep -q 'secrets.DOCKER_USERNAME' .github/workflows/image-retention.yml`
- `! grep -riq 'anihilat' .github/workflows/`
- `python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ['.github/workflows/release-please.yml','.github/workflows/image-retention.yml']]"`

## Touchpoints
- `.github/workflows/release-please.yml` — dispatch step `if:` guard.
- `.github/workflows/image-retention.yml` — new.

## Open questions
- Keep count for `sha-*` on Docker Hub: start at 10 (env `KEEP_SHA`).
- Cron cadence: weekly (Mon 04:00 UTC).

## Implementation notes
- **Dispatch fix.** Changed the guard on the "Build the release image" step
  from `if: ${{ steps.release.outputs.release_created }}` (implicit
  `success()` of the prior step) to
  `if: ${{ always() && steps.release.outputs.release_created == 'true' }}`.
  release-please sets its outputs when it creates the release, *before* the
  locked-PR comment that throws, so the build now fires regardless of that
  cosmetic failure. The release-please step may still show red — that is the
  locked-comment, not the release; the image is what we care about.
- **Why not fix the locking here.** Every recent merged PR is `locked=true`
  with no reason and there is no lock workflow in this repo, so the locker is
  a repo setting / external app, out of scope for a workflow PR. The
  `always()` guard makes the image build independent of it, which is the
  durable fix either way.
- **Retention — only `sha-*`, never semver/main.** Docker Hub prune selects
  strictly `^sha-` tags, sorts by `last_updated` desc, keeps `KEEP_SHA=10`,
  deletes the tail. `main`/`latest`/semver are unreachable by the selector.
  Manual dispatch defaults to `dry_run: true` (list only); the weekly cron
  prunes for real. A `concurrency` group stops a manual run and the cron
  from overlapping.
- **GHCR dropped from scope (review finding).** The first draft added an
  `actions/delete-package-versions@v5` "delete untagged" job for GHCR; the
  reviewer correctly flagged that provenance attestations make tagged images
  OCI indexes whose children are *untagged* versions, so that job would
  corrupt tagged images. Removed; see Scope → Does NOT cover.
- **Secrets / privacy.** The prune job sets `environment: DOCKER_HUB` to reach
  `DOCKER_USERNAME`/`DOCKER_TOKEN` (same gate as `docker.yml`); the namespace
  is read from the secret, never hard-coded, so the `anihilat` handle stays
  out of this repo.
- **Docker Hub auth.** `POST /v2/users/login/` with the PAT as `password`
  yields a JWT; API calls use `Authorization: JWT <token>`. The PAT needs
  **delete** scope, or the `DELETE /tags/<name>/` call returns 401/403 —
  `DOCKER_TOKEN` may need widening from the push-only scope docker.yml uses.
