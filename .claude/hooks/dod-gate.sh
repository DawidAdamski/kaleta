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
#
# If the judge cannot run at all (missing file, interpreter or import failure),
# this wrapper fails closed and ends the run: result=escalated, mode D. A hook
# error code would just let the session stop unjudged; a block would repeat
# forever without counting toward max-attempts.
set -uo pipefail

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root" || exit 0
if [ ! -f .claude/state/active-plan ]; then cat >/dev/null; exit 0; fi

broken() {
  local msg="DoD gate could not run ($1) — the harness is broken. The owner must fix it; the gate will not decide this run."
  if [ "${DOD_GATE_DRY:-0}" = 1 ]; then
    jq -n --arg r "$msg" '{decision:"block", reason:$r}'
    exit 0
  fi
  case "$(cat .claude/state/result 2>/dev/null)" in
    escalated|exhausted|blocked) exit 0 ;;   # already terminal
  esac
  echo escalated > .claude/state/result
  echo D > .claude/state/mode
  printf '%s\n' "$msg" > .claude/state/escalated-reason
  echo "dod-gate: ESCALATED — $msg" >&2
  exit 0
}

if [ ! -f scripts/harness/gate.py ] || [ ! -f scripts/harness/python.sh ]; then
  cat >/dev/null
  broken "scripts/harness/gate.py or python.sh is missing"
fi
# shellcheck source=../../scripts/harness/python.sh
. scripts/harness/python.sh
out=$("${HARNESS_PY[@]}" scripts/harness/gate.py 2>.claude/state/gate-stderr.log)
rc=$?
cat .claude/state/gate-stderr.log >&2
[ "$rc" -eq 0 ] || broken "exit $rc: $(tail -n 1 .claude/state/gate-stderr.log 2>/dev/null)"
printf '%s' "$out"
