#!/usr/bin/env bash
# schemathesis API-fuzzing runner for Kaleta.
#
# Property-based fuzzing of the API against its own OpenAPI schema
# (`/api-docs/openapi.json`): schemathesis generates edge-case inputs for every
# documented `/api/v1` operation and checks the responses. The security value is
# `not_a_server_error` — no fuzzed input should crash a handler into a 5xx.
#
# Part of the security assessment (docs/security/). Needs a live instance with
# the API docs mounted (debug, or KALETA_API_DOCS=true). schemathesis is a
# Python dev tool, run via uv like audit_deps.sh:
#   uv sync --group dev
#
# Every /api/v1 route except health is behind bearer auth, so an unauthenticated
# fuzz gets a 401 before the handler — enough to prove the auth layer never
# 5xxes, but not to reach handler logic. The default check is therefore
# `not_a_server_error` (meaningful with or without a token, low noise). For a
# deeper authenticated conformance fuzz, pass a real bearer and all checks:
#   ST_BEARER=<token> ST_CHECKS=all ./scripts/security/scan_schemathesis.sh
# (a token needs an active family + unlocked keyring — a seeded/staging run).
#
# Usage:
#   ./scripts/security/scan_schemathesis.sh                      # http://localhost:8080
#   ./scripts/security/scan_schemathesis.sh http://localhost:8090
#   ST_CHECKS=all ST_BEARER=kt_... ./scripts/security/scan_schemathesis.sh
#
# Environment overrides:
#   ST_SCHEMA        full schema URL (default <base>/api-docs/openapi.json)
#   ST_CHECKS        checks to run (default not_a_server_error; e.g. all)
#   ST_MAX_EXAMPLES  generated examples per operation (default 50)
#   ST_BEARER        bearer token; adds an Authorization header when set.
#                    NB: it is then visible in the process list — a local
#                    operator tool, so acceptable, but do not use it where other
#                    users can read `ps`.
#   ST_REPORT_DIR    when set, write the JSON run report here
set -euo pipefail
cd "$(dirname "$0")/../.."

TARGET="${1:-http://localhost:8080}"
TARGET="${TARGET%/}"  # one trailing slash off, so schema URL and --url agree
ST_SCHEMA="${ST_SCHEMA:-${TARGET}/api-docs/openapi.json}"
ST_CHECKS="${ST_CHECKS:-not_a_server_error}"
ST_MAX_EXAMPLES="${ST_MAX_EXAMPLES:-50}"

args=(run "$ST_SCHEMA" --url "$TARGET" --checks "$ST_CHECKS" --max-examples "$ST_MAX_EXAMPLES")
[[ -n "${ST_BEARER:-}" ]] && args+=(--header "Authorization: Bearer ${ST_BEARER}")
if [[ -n "${ST_REPORT_DIR:-}" ]]; then
    mkdir -p "$ST_REPORT_DIR"
    args+=(--report json --report-dir "$ST_REPORT_DIR")
fi

echo "== schemathesis ${ST_CHECKS} (schema=$ST_SCHEMA url=$TARGET max-examples=$ST_MAX_EXAMPLES${ST_BEARER:+ auth=on}) =="
exec uv run --no-sync schemathesis "${args[@]}"
