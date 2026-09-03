#!/usr/bin/env bash
# Goal-mode state for one plan from docs/plans/.
#
#   scripts/plan_goal.sh start <plan_id> [--max-attempts N]   arm the DoD gate for this plan
#   scripts/plan_goal.sh status                                show current goal state
#   scripts/plan_goal.sh block "<reason>"                      let the session stop: work is blocked
#   scripts/plan_goal.sh finish                                disarm the gate (after PR is opened)
#   scripts/plan_goal.sh check                                 run the DoD judge now (no attempt counted); exit 1 if not done
#
# The Stop hook (.claude/hooks/dod-gate.sh) is active only while
# .claude/state/active-plan exists. Everything here is plain files so the
# same flow works from Claude Code, Cursor, or a headless runner.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
state=.claude/state
mkdir -p "$state"

cmd=${1:-status}
case "$cmd" in
  start)
    plan_id=${2:?usage: plan_goal.sh start <plan_id> [--max-attempts N]}
    max=6
    if [ "${3:-}" = "--max-attempts" ]; then max=${4:?N}; fi
    plan="docs/plans/$plan_id.md"
    [ -f "$plan" ] || { echo "plan_goal: $plan not found" >&2; exit 1; }
    status=$(grep -m1 '^status:' "$plan" | sed -E 's/^status:[[:space:]]*//')
    case "$status" in
      draft|in-progress) ;;
      *) echo "plan_goal: plan status is '$status' — only draft/in-progress can be started" >&2; exit 1 ;;
    esac
    branch=$(git rev-parse --abbrev-ref HEAD)
    if [ "$branch" = "main" ]; then
      git checkout -b "plan/$plan_id"
    elif [ "$branch" != "plan/$plan_id" ]; then
      echo "plan_goal: note — you are on '$branch', not main or plan/$plan_id (1 plan = 1 branch = 1 PR)" >&2
    fi
    if [ "$status" = "draft" ]; then
      sed -i.bak -E 's/^status:[[:space:]]*draft/status: in-progress/' "$plan" && rm -f "$plan.bak"
    fi
    printf '%s' "$plan_id" > "$state/active-plan"
    printf '%s' "$max" > "$state/max-attempts"
    rm -f "$state/attempts" "$state/result" "$state/blocked-reason" "$state/review-verdict.json" "$state/review-raw.json"
    echo "plan_goal: armed DoD gate for '$plan_id' on branch $(git rev-parse --abbrev-ref HEAD) (max attempts: $max)"
    ;;
  status)
    if [ ! -f "$state/active-plan" ]; then echo "plan_goal: no active plan (gate disarmed)"; exit 0; fi
    echo "plan:      $(cat "$state/active-plan")"
    echo "branch:    $(git rev-parse --abbrev-ref HEAD)"
    echo "attempts:  $(cat "$state/attempts" 2>/dev/null || echo 0)/$(cat "$state/max-attempts")"
    echo "result:    $(cat "$state/result" 2>/dev/null || echo '-')"
    if [ -f "$state/review-verdict.json" ]; then
      echo "review:    $(jq -r '.verdict + " (" + (.reviewers|join(", ")) + ", diff " + .diff_hash + ")"' "$state/review-verdict.json")"
    else
      echo "review:    none yet"
    fi
    [ -f "$state/blocked-reason" ] && echo "blocked:   $(cat "$state/blocked-reason")"
    ;;
  block)
    reason=${2:?usage: plan_goal.sh block "<reason>"}
    echo blocked > "$state/result"
    printf '%s\n' "$reason" > "$state/blocked-reason"
    echo "plan_goal: marked BLOCKED — the gate will let the session stop. Reason: $reason"
    ;;
  check)
    [ -f "$state/active-plan" ] || { echo "plan_goal: no active plan — run: plan_goal.sh start <plan_id>" >&2; exit 1; }
    out=$(echo '{}' | DOD_GATE_DRY=1 .claude/hooks/dod-gate.sh 2>/tmp/plan_goal_check.err)
    cat /tmp/plan_goal_check.err >&2
    if [ -n "$out" ]; then printf '%s\n' "$out" | jq -r '.reason'; exit 1; fi
    echo "plan_goal: DoD gate PASSED for $(cat "$state/active-plan")"
    ;;
  finish)
    rm -f "$state/active-plan" "$state/attempts" "$state/max-attempts" "$state/result" "$state/blocked-reason"
    echo "plan_goal: gate disarmed (review verdict kept for reference)"
    ;;
  *)
    echo "usage: plan_goal.sh start <plan_id> [--max-attempts N] | status | check | block \"<reason>\" | finish" >&2; exit 1 ;;
esac
