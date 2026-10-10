#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# The PostgreSQL the test suite runs against (ADR-38: there is no other).
#
#   ./scripts/test_db.sh up     start it (idempotent) and wait until it answers
#   ./scripts/test_db.sh down   remove it — its data lives in tmpfs, nothing is kept
#   ./scripts/test_db.sh url    print the KALETA_DB_URL the tests default to
#
# postgres:16-alpine under podman (or docker) on 127.0.0.1:55432, with fsync
# off and the data directory in tmpfs: a throwaway server, fast because it
# promises nothing. Never point it at data you want to keep.
set -euo pipefail

NAME="${KALETA_TEST_DB_CONTAINER:-kaleta-testpg}"
PORT="${KALETA_TEST_DB_PORT:-55432}"
IMAGE="docker.io/library/postgres:16-alpine"
URL="postgresql+asyncpg://kaleta:kaleta@127.0.0.1:${PORT}/kaleta"

engine() {
  if command -v podman >/dev/null 2>&1; then
    echo podman
  elif command -v docker >/dev/null 2>&1; then
    echo docker
  else
    echo "test_db.sh: neither podman nor docker is installed" >&2
    exit 1
  fi
}

up() {
  local ce
  ce="$(engine)"
  if [[ "$("$ce" ps --filter "name=^${NAME}$" --format '{{.Names}}')" != "$NAME" ]]; then
    # A stopped container of that name holds nothing (tmpfs): replace it.
    "$ce" rm -f "$NAME" >/dev/null 2>&1 || true
    "$ce" run -d --name "$NAME" \
      -e POSTGRES_USER=kaleta -e POSTGRES_PASSWORD=kaleta -e POSTGRES_DB=kaleta \
      -p "127.0.0.1:${PORT}:5432" \
      --tmpfs /var/lib/postgresql/data \
      "$IMAGE" \
      -c fsync=off -c synchronous_commit=off -c full_page_writes=off \
      -c max_connections=300 >/dev/null
  fi
  for _ in $(seq 1 60); do
    if "$ce" exec "$NAME" pg_isready -U kaleta -d kaleta >/dev/null 2>&1; then
      echo "$URL"
      return 0
    fi
    sleep 0.5
  done
  echo "test_db.sh: $NAME did not become ready" >&2
  exit 1
}

down() {
  "$(engine)" rm -f "$NAME" >/dev/null 2>&1 || true
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  url) echo "$URL" ;;
  *)
    echo "usage: $0 up|down|url" >&2
    exit 2
    ;;
esac
