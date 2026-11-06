#!/usr/bin/env bash
# Stop hook — deterministic Definition-of-Done judge for goal mode (ADR-39).
#
# Active only while .claude/state/active-plan exists (set by scripts/plan_goal.sh
# start). Otherwise it exits 0 at once and Claude Code behaves normally.
#
# The judge itself is scripts/harness/gate.py: it collects the evidence, decides,
# writes a record to docs/harness/runs/<plan_id>.jsonl and prints
# {"decision":"block","reason":...} when the plan is not done yet. Bounded by
# .claude/state/max-attempts (default 6); after that the session may stop and
# .claude/state/result is "exhausted". DOD_GATE_DRY=1 (plan_goal.sh check)
# judges without counting an attempt.
set -uo pipefail

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root" || exit 0
if [ ! -f .claude/state/active-plan ]; then cat >/dev/null; exit 0; fi

if [ ! -f scripts/harness/gate.py ] || [ ! -f scripts/harness/python.sh ]; then
  cat >/dev/null
  jq -n '{decision:"block", reason:"DoD gate: scripts/harness/gate.py is missing — the harness is broken. Tell the maintainer; do not work around it."}'
  exit 0
fi
# shellcheck source=../../scripts/harness/python.sh
. scripts/harness/python.sh
exec "${HARNESS_PY[@]}" scripts/harness/gate.py
