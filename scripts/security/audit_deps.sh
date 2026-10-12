#!/usr/bin/env bash
# Dependency advisory audit — fails if any pinned dependency has a known
# vulnerability (PyPI/OSV advisory database via pip-audit).
#
# Part of the security assessment (docs/security/). Headless, CI-safe.
# Requires the dev dependency group:
#   uv sync --group dev
#
# Usage: ./scripts/security/audit_deps.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

# --skip-editable drops the local `kaleta` package itself (not on PyPI, nothing
# to audit); every third-party dependency is still checked.
exec uv run --no-sync pip-audit --progress-spinner=off --skip-editable "$@"
