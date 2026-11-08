#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Sourced by the hooks and gate scripts: sets HARNESS_PY (an array) to the
# interpreter that runs scripts/harness/*.py. The harness is stdlib-only.
#   KALETA_HARNESS_PY   explicit override (tests, CI)
#   uv + pyproject.toml the project's interpreter (laptop, worktrees)
#   python3             fallback
if [ -n "${KALETA_HARNESS_PY:-}" ]; then
  read -r -a HARNESS_PY <<< "$KALETA_HARNESS_PY"
elif command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  HARNESS_PY=(uv run --no-sync python)
else
  HARNESS_PY=(python3)
fi
export HARNESS_PY
