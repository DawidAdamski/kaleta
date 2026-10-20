#!/usr/bin/env bash
# Trivy security scanner for Kaleta.
#
# Complements audit_deps.sh (pip-audit, Python package advisories only) with
# the layers pip-audit cannot see:
#   fs      filesystem vulnerability scan (reads uv.lock + the rest of the tree)
#   config  IaC / Containerfile misconfiguration (Containerfile*, compose, deploy/)
#   secret  accidentally committed secrets
#   image   OS-package CVEs in a built container image
#   all     fs + config + secret (the server-less modes), run in sequence
#
# Runner: a local `trivy` binary when present, otherwise the official container
# image via docker or podman (the repo already uses both for the test DB).
#
# Part of the security assessment (docs/security/). Headless and CI-safe for
# the fs/config/secret modes; `image` needs a built image or a registry ref.
#
# Usage:
#   ./scripts/security/scan_trivy.sh fs
#   ./scripts/security/scan_trivy.sh config
#   ./scripts/security/scan_trivy.sh secret
#   ./scripts/security/scan_trivy.sh image <image-ref>
#   ./scripts/security/scan_trivy.sh all
#
# Environment overrides:
#   TRIVY_VERSION   pinned Trivy version (default 0.76.0)
#   TRIVY_SEVERITY  severity gate; a finding at/above it exits non-zero
#                   (default HIGH,CRITICAL)
#   TRIVY_IMAGE     full image ref for the container runner
#                   (default aquasec/trivy:$TRIVY_VERSION)
#   TRIVY_RUNNER    force the runner: trivy | docker | podman
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO="$PWD"

TRIVY_VERSION="${TRIVY_VERSION:-0.76.0}"
TRIVY_SEVERITY="${TRIVY_SEVERITY:-HIGH,CRITICAL}"
TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:${TRIVY_VERSION}}"

# The filesystem walk (fs / config / secret) must look at the source tree — the
# dependency *source* (uv.lock), our code and our deploy files — not installed
# virtualenvs, the VCS metadata, or the agent worktrees under .claude. Scanning
# a .venv would re-report CVEs for bundled front-end assets (NiceGUI ships
# npm libraries) and for whatever an isolated worktree happens to have synced,
# none of which is what we deploy.
TRIVY_SKIP_DIRS="${TRIVY_SKIP_DIRS:-.git,.venv,.claude,**/.venv,**/node_modules,**/site-packages}"

# Cache the vulnerability DB between runs so repeated scans are fast.
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/trivy"
mkdir -p "$CACHE_DIR"

pick_runner() {
    if [[ -n "${TRIVY_RUNNER:-}" ]]; then
        case "$TRIVY_RUNNER" in
            trivy | docker | podman) echo "$TRIVY_RUNNER" ;;
            *)
                echo "scan_trivy: TRIVY_RUNNER must be trivy|docker|podman, got '$TRIVY_RUNNER'" >&2
                exit 2
                ;;
        esac
        return
    fi
    if command -v trivy >/dev/null 2>&1; then
        echo trivy
    elif command -v docker >/dev/null 2>&1; then
        echo docker
    elif command -v podman >/dev/null 2>&1; then
        echo podman
    else
        echo "scan_trivy: need a 'trivy' binary or docker/podman to run it" >&2
        exit 127
    fi
}

RUNNER="$(pick_runner)"

# Run a filesystem-oriented trivy mode (fs / config / secret) against the repo.
# For the container runners the repo is mounted read-only at /work and the DB
# cache is shared from the host. `image` mode does not go through here — it has
# its own path (scan_image) so a locally built image works on both engines.
run_trivy() {
    local mode="$1"
    shift
    case "$RUNNER" in
        trivy)
            trivy "$mode" "$@"
            ;;
        docker | podman)
            "$RUNNER" run --rm \
                -v "$REPO":/work:ro \
                -v "$CACHE_DIR":/root/.cache/trivy \
                -w /work \
                "$TRIVY_IMAGE" "$mode" "$@"
            ;;
        *)
            echo "scan_trivy: unsupported runner '$RUNNER'" >&2
            exit 2
            ;;
    esac
}

scan_fs() {
    echo "== trivy fs (vuln scan of the dependency source) =="
    run_trivy fs --scanners vuln --severity "$TRIVY_SEVERITY" \
        --skip-dirs "$TRIVY_SKIP_DIRS" --exit-code 1 --no-progress .
}

scan_config() {
    echo "== trivy config (IaC / Containerfile misconfig) =="
    # Containerfile / Containerfile.full use Podman naming, so teach Trivy's
    # Dockerfile parser to treat them as Dockerfiles. `config` has no
    # --no-progress flag (it prints no progress bar).
    run_trivy config --severity "$TRIVY_SEVERITY" --exit-code 1 \
        --skip-dirs "$TRIVY_SKIP_DIRS" \
        --file-patterns "dockerfile:Containerfile*" .
}

scan_secret() {
    echo "== trivy fs (secret scan) =="
    run_trivy fs --scanners secret --severity "$TRIVY_SEVERITY" \
        --skip-dirs "$TRIVY_SKIP_DIRS" --exit-code 1 --no-progress .
}

scan_image() {
    local ref="${1:-}"
    if [[ -z "$ref" ]]; then
        echo "scan_trivy: 'image' mode needs an image ref, e.g. kaleta:local" >&2
        exit 2
    fi
    echo "== trivy image $ref =="
    local sev=(--severity "$TRIVY_SEVERITY" --exit-code 1 --no-progress)

    if [[ "$RUNNER" == "trivy" ]]; then
        trivy image "${sev[@]}" "$ref"
        return
    fi

    # Container runner. A locally built image is not in any registry, so Trivy
    # running inside its own container cannot pull it. Hand such an image over
    # as a saved docker-archive via --input — engine-agnostic and needing no
    # socket mount (works the same under docker and podman). A ref that is not
    # present locally is assumed to be a registry ref and scanned directly.
    if "$RUNNER" image inspect "$ref" >/dev/null 2>&1; then
        local tar
        tar="$(mktemp -t trivy-img-XXXXXX)"
        # shellcheck disable=SC2064  # expand $tar now so the trap is self-contained
        trap "rm -f '$tar'" RETURN
        "$RUNNER" save -o "$tar" "$ref"
        "$RUNNER" run --rm \
            -v "$tar":/img.tar:ro \
            -v "$CACHE_DIR":/root/.cache/trivy \
            "$TRIVY_IMAGE" image --input /img.tar "${sev[@]}"
    else
        "$RUNNER" run --rm \
            -v "$CACHE_DIR":/root/.cache/trivy \
            "$TRIVY_IMAGE" image "${sev[@]}" "$ref"
    fi
}

mode="${1:-all}"
case "$mode" in
    fs) scan_fs ;;
    config) scan_config ;;
    secret) scan_secret ;;
    image)
        shift
        scan_image "$@"
        ;;
    all)
        scan_fs
        scan_config
        scan_secret
        ;;
    *)
        echo "scan_trivy: unknown mode '$mode' (fs | config | secret | image | all)" >&2
        exit 2
        ;;
esac
