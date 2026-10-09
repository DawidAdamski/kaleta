#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Smoke-test a hosted Kaleta: sign up, log in, unlock, POST one transaction,
# GET it back, delete the account (scripts/hosted_smoke.py does the walking).
#
#   ./scripts/hosted_smoke.sh https://kaleta.example.com   # a deployed instance
#   ./scripts/hosted_smoke.sh                              # the hosted-dev stack
#
# With no URL it brings up compose.hosted-dev.yml (PostgreSQL + Kaleta in
# `multi` mode with the debug sign-in backend), waits for it to be healthy,
# runs the smoke against it and takes the stack down again, volumes included.
# KALETA_HOSTED_DEV_PORT picks the port (default 8090); KALETA_SMOKE_KEEP=1
# leaves the stack running afterwards. Needs podman (or docker) compose.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ $# -gt 0 ]]; then
  exec uv run python scripts/hosted_smoke.py "$@"
fi

if command -v podman >/dev/null 2>&1; then
  compose=(podman compose -f compose.hosted-dev.yml)
elif command -v docker >/dev/null 2>&1; then
  compose=(docker compose -f compose.hosted-dev.yml)
else
  echo "hosted_smoke: no URL given and neither podman nor docker is installed" >&2
  exit 2
fi

port="${KALETA_HOSTED_DEV_PORT:-8090}"
base="http://localhost:${port}"

cleanup() {
  if [[ "${KALETA_SMOKE_KEEP:-0}" != "1" ]]; then
    "${compose[@]}" down -v >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "hosted_smoke: starting compose.hosted-dev.yml on ${base}"
"${compose[@]}" up -d --build >/dev/null

for _ in $(seq 1 120); do
  if curl -fsS "${base}/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! curl -fsS "${base}/api/v1/health" >/dev/null 2>&1; then
  echo "hosted_smoke: the stack did not become healthy; last app logs:" >&2
  "${compose[@]}" logs --tail 40 kaleta >&2 || true
  exit 1
fi

uv run python scripts/hosted_smoke.py "${base}"
