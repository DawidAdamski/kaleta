#!/usr/bin/env bash
# OWASP ZAP baseline scanner for Kaleta.
#
# The baseline is a *passive* scan: ZAP spiders the target and runs its passive
# rules on what comes back. It sends no attack payloads, so it is safe to point
# at our own running instance. It catches unauthenticated-surface hygiene a
# static pass cannot — missing/weak security headers (CSP,
# X-Frame-Options/frame-ancestors, X-Content-Type-Options, Permissions-Policy),
# cookie flags over HTTP, and information disclosure in responses.
#
# Part of the security assessment (docs/security/). Complements the server-less
# Trivy / pip-audit checks with one that needs a live instance.
#
# ZAP ships as a container image (there is no common local binary), so this
# runner always uses docker or podman. The scanned app runs on the host, so the
# container reaches it through host.docker.internal when the target host is
# localhost/127.0.0.1 (any other host is passed through unchanged). That needs
# Docker 20.10+/Desktop or Podman 4.1+, and the app listening on 0.0.0.0 (the
# default KALETA_HOST) — on Linux Docker the gateway is the bridge IP, so an app
# bound only to 127.0.0.1 would be unreachable from the container.
#
# Start an instance first, e.g.:
#   ./scripts/test_db.sh up
#   KALETA_SECRET_KEY=dev-only uv run kaleta   # http://localhost:8080
#
# Usage:
#   ./scripts/security/scan_zap.sh                     # scans http://localhost:8080
#   ./scripts/security/scan_zap.sh http://localhost:8090
#   ZAP_FAIL_ON=WARN ./scripts/security/scan_zap.sh    # also fail the gate on WARN
#   ZAP_REPORT_DIR=/tmp/zap ./scripts/security/scan_zap.sh   # also write html+json reports
#
# Environment overrides:
#   ZAP_VERSION      pinned ZAP image tag (default 2.16.1)
#   ZAP_IMAGE        full image ref (default ghcr.io/zaproxy/zaproxy:$ZAP_VERSION)
#   ZAP_RUNNER       force the runner: docker | podman
#   ZAP_FAIL_ON      gate threshold: FAIL (default) or WARN. FAIL ignores
#                    warnings for the exit code (still printed); WARN fails on
#                    either.
#   ZAP_SPIDER_MINS  spider time budget in minutes (default 1)
#   ZAP_REPORT_DIR   when set, ZAP also writes report.html + report.json here.
#                    The dir is mounted into the container and must be writable
#                    by the ZAP user (uid 1000); the script makes it so.
set -euo pipefail
cd "$(dirname "$0")/../.."

ZAP_VERSION="${ZAP_VERSION:-2.16.1}"
ZAP_IMAGE="${ZAP_IMAGE:-ghcr.io/zaproxy/zaproxy:${ZAP_VERSION}}"
ZAP_FAIL_ON="${ZAP_FAIL_ON:-FAIL}"
ZAP_SPIDER_MINS="${ZAP_SPIDER_MINS:-1}"

TARGET="${1:-http://localhost:8080}"

pick_runner() {
    if [[ -n "${ZAP_RUNNER:-}" ]]; then
        case "$ZAP_RUNNER" in
            docker | podman) echo "$ZAP_RUNNER" ;;
            *)
                echo "scan_zap: ZAP_RUNNER must be docker|podman, got '$ZAP_RUNNER'" >&2
                exit 2
                ;;
        esac
        return
    fi
    if command -v docker >/dev/null 2>&1; then
        echo docker
    elif command -v podman >/dev/null 2>&1; then
        echo podman
    else
        echo "scan_zap: need docker or podman to run the ZAP container image" >&2
        exit 127
    fi
}

case "$ZAP_FAIL_ON" in
    FAIL | WARN) ;;
    *)
        echo "scan_zap: ZAP_FAIL_ON must be FAIL|WARN, got '$ZAP_FAIL_ON'" >&2
        exit 2
        ;;
esac

RUNNER="$(pick_runner)"

# The app runs on the host; from inside the container 'localhost' is the
# container itself. When the target's *host* is localhost/127.0.0.1, rewrite it
# to host.docker.internal and map that to the host gateway. Requires Docker
# 20.10+/Desktop or Podman 4.1+, and the app listening on 0.0.0.0 (the default
# KALETA_HOST) — on Linux Docker the gateway is the bridge IP, so an app bound
# only to 127.0.0.1 is not reachable. A non-local target is left untouched.
scan_target="$TARGET"
add_host=()
if [[ "$TARGET" =~ ^https?://(localhost|127\.0\.0\.1)([:/]|$) ]]; then
    local_host="${BASH_REMATCH[1]}"
    # Replace only the first occurrence, which the anchored match proves is the
    # authority host — not a 'localhost' sitting later in a path or query.
    scan_target="${TARGET/$local_host/host.docker.internal}"
    add_host=(--add-host "host.docker.internal:host-gateway")
fi

# -I  do not fail the run on WARN (only FAIL); dropped when the gate is WARN.
baseline_opts=(-t "$scan_target" -m "$ZAP_SPIDER_MINS")
[[ "$ZAP_FAIL_ON" == "FAIL" ]] && baseline_opts+=(-I)

mount_opts=()
if [[ -n "${ZAP_REPORT_DIR:-}" ]]; then
    mkdir -p "$ZAP_REPORT_DIR"
    # Resolve to an absolute path: we have already cd'd to the repo root, so a
    # relative dir would be created there, and a bare name with no slash would
    # be read as a *named volume* rather than a host bind mount.
    ZAP_REPORT_DIR="$(cd "$ZAP_REPORT_DIR" && pwd)"
    # ZAP writes reports as uid 1000 into /zap/wrk; make the bind mount writable.
    chmod a+rwx "$ZAP_REPORT_DIR"
    mount_opts=(-v "$ZAP_REPORT_DIR":/zap/wrk:rw)
    baseline_opts+=(-r report.html -J report.json)
fi

echo "== ZAP baseline ($RUNNER) target=$TARGET as=$scan_target fail-on=$ZAP_FAIL_ON =="

# No `-t`: a headless/CI runner must not allocate a TTY. Under nohup or a CI
# runner there is no terminal, and a TTY there detaches the container (the
# wrapper returns early with a truncated log while the scan keeps running).
set +e
"$RUNNER" run --rm \
    ${add_host[@]+"${add_host[@]}"} \
    ${mount_opts[@]+"${mount_opts[@]}"} \
    "$ZAP_IMAGE" zap-baseline.py "${baseline_opts[@]}"
status=$?
set -e

if [[ -n "${ZAP_REPORT_DIR:-}" ]]; then
    echo "scan_zap: reports written to $ZAP_REPORT_DIR (report.html, report.json)"
fi

# zap-baseline.py exit codes:
#   0  nothing at/above the gate — with -I (our FAIL default) warnings count as
#      PASS, so warnings-only still exits 0
#   1  at least one FAIL
#   2  warnings only, no FAIL — reachable *only* without -I, i.e. ZAP_FAIL_ON=WARN
#   3+ a run/usage error (not a scan result)
# So under the default FAIL gate we only ever see 0, 1 or 3+; exit 2 belongs to
# the WARN gate and is a gate failure there.
case "$status" in
    0) echo "scan_zap: no FAIL at/above the $ZAP_FAIL_ON gate — passed"; exit 0 ;;
    1) echo "scan_zap: baseline reported a FAIL — gate failed" >&2; exit 1 ;;
    2) echo "scan_zap: warnings present (ZAP_FAIL_ON=WARN) — gate failed" >&2; exit 1 ;;
    *) echo "scan_zap: ZAP exited $status (run error, not a clean scan)" >&2; exit "$status" ;;
esac
