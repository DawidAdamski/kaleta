#!/usr/bin/env bash
# Definition-of-Done gate. Run before claiming any task complete.
# Usage: ./scripts/verify.sh [--e2e]
set -euo pipefail
cd "$(dirname "$0")/.."

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
