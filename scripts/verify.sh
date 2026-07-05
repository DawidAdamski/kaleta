#!/usr/bin/env bash
# Definition-of-Done gate. Run before claiming any task complete.
#
# Requires dev dependency group (ruff, mypy, import-linter, pytest, …):
#   uv sync --group dev
#
# Usage: ./scripts/verify.sh [--e2e]
set -euo pipefail
cd "$(dirname "$0")/.."

require_dev_tools() {
  local tool missing=()
  for tool in ruff mypy lint-imports; do
    if ! uv run --no-sync "$tool" --version &>/dev/null; then
      missing+=("$tool")
    fi
  done
  if ((${#missing[@]} > 0)); then
    echo "verify.sh: missing dev tools: ${missing[*]}" >&2
    echo "Run: uv sync --group dev" >&2
    exit 1
  fi
}

require_dev_tools

echo "==> ruff check"
uv run ruff check .
echo "==> ruff format"
uv run ruff format --check .
echo "==> mypy"
uv run mypy src/
echo "==> import-linter (architecture contracts)"
uv run lint-imports
echo "==> unit + integration tests"
uv run pytest tests/unit tests/integration -q
echo "==> spec coverage (BDD <-> tests)"
uv run python scripts/spec_coverage.py
echo "==> doc link checker"
uv run python scripts/check_doc_links.py

# E2e: explicit via --e2e, or FORCED when views/ changed (Working Agreement rule 8).
RUN_E2E="${1:-}"
if [[ "$RUN_E2E" != "--e2e" ]] && ! git diff --quiet HEAD -- src/kaleta/views/ 2>/dev/null; then
  echo "==> views/ changed since HEAD — e2e is mandatory (rule 8)"
  RUN_E2E="--e2e"
fi

if [[ "$RUN_E2E" == "--e2e" ]]; then
  echo "==> e2e (ephemeral instance)"
  uv run pytest tests/e2e/ -q
fi

echo ""
echo "VERIFY OK$( [[ "$RUN_E2E" == "--e2e" ]] && echo " (incl. e2e)" )"
