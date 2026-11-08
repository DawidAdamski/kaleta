#!/usr/bin/env bash
# PreToolUse guard (Edit|Write|MultiEdit).
# The agent may not edit its own harness, the owner's rules, frozen history,
# or applied migrations. The list lives in docs/harness/protected-paths.txt.
#
# Maintainer mode (ADR-39): KALETA_HARNESS_MAINTAINER=1 in *this hook's*
# environment lets the edit through. Hooks inherit the environment of the
# process that launched Claude Code (`KALETA_HARNESS_MAINTAINER=1 claude`);
# the agent's Bash tool runs in a child shell and cannot change it.
#
# Exit 2 = block the tool call and feed the message back to Claude.
set -uo pipefail

input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)
[ -z "$path" ] && exit 0

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
rel=${path#"$root"/}

# shellcheck source=../../scripts/harness/protected-lib.sh
if ! . "$root/scripts/harness/protected-lib.sh" 2>/dev/null; then
  echo "protect-files: scripts/harness/protected-lib.sh is missing — every edit is refused until the maintainer restores it" >&2
  exit 2
fi
export HARNESS_ROOT=$root

harness_protected "$rel" edit || exit 0

if [ "${KALETA_HARNESS_MAINTAINER:-0}" = 1 ]; then
  echo "protect-files: maintainer edit $rel" >&2
  exit 0
fi

case "$rel" in
  docs/plans/archive/*) echo "protect-files: archived plans are frozen ($rel)." >&2 ;;
  alembic/versions/*)   echo "protect-files: existing migrations are immutable — create a new revision instead ($rel)." >&2 ;;
  *)                    echo "protect-files: $rel belongs to the harness or the owner's rules (docs/harness/protected-paths.txt) and is read-only for the agent. Ask the maintainer." >&2 ;;
esac
exit 2
