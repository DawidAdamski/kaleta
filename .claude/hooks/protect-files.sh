#!/usr/bin/env bash
# PreToolUse guard (Edit|Write|MultiEdit).
# The agent may not edit its own harness, frozen history, or applied migrations.
# Exit 2 = block the tool call and feed the message back to Claude.
set -uo pipefail

input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)
[ -z "$path" ] && exit 0

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
rel=${path#"$root"/}

deny() { echo "protect-files: $1" >&2; exit 2; }

case "$rel" in
  .claude/hooks/*|.claude/settings.json|.claude/state/*|.claude/commands/implement-plan.md)
    deny "harness files are read-only for the agent ($rel). Ask the maintainer." ;;
  scripts/verify.sh|scripts/review_gate.sh|scripts/plan_goal.sh|scripts/plan_runner.sh)
    deny "the DoD gate scripts are read-only for the agent ($rel). Ask the maintainer." ;;
  docs/plans/archive/*)
    deny "archived plans are frozen ($rel)." ;;
  alembic/versions/*)
    if git -C "$root" ls-files --error-unmatch "$rel" >/dev/null 2>&1; then
      deny "existing migrations are immutable — create a new revision instead ($rel)."
    fi ;;
esac
exit 0
