#!/usr/bin/env bash
# Headless plan runner — the "queue consumer" for docs/plans/.
#
# For each selected plan: git worktree from main → arm the DoD gate →
# fresh `claude -p` session with the same prompt as /implement-plan →
# read the gate result → (optionally) push + open PR. One plan = one
# worktree = one branch = one PR. Nothing is merged automatically.
#
#   scripts/plan_runner.sh [options] [plan_id ...]
#
# Selection (when no plan_id given):
#   --status draft|in-progress   default: draft
#   --effort small|medium|large  default: small
#   --max N                      stop after N plans (default: all selected)
# Behaviour:
#   --pr                         push the branch and open a PR when the gate says done
#   --max-turns T                claude -p turn limit (default: 80)
#   --max-attempts N             DoD gate attempts per plan (default: 6)
#   --model M                    model for the implementer (default: Claude Code default)
#   --engine claude|cursor       which CLI runs the implementer (default: claude). cursor = Cursor CLI `agent -p`;
#                                the DoD judge is then scripts/plan_goal.sh check in a Ralph-style loop
#   --dry-run                    only print what would run
#
# Env: KALETA_CROSS_REVIEW=1 (+ KALETA_CROSS_REVIEW_MODEL) is passed through
# to scripts/review_gate.sh inside the session.
set -euo pipefail
repo=$(git rev-parse --show-toplevel); cd "$repo"
wt_root="$(dirname "$repo")/$(basename "$repo")-worktrees"
log_root="$repo/logs/plans"; mkdir -p "$log_root"

status_f=draft; effort_f=small; max_n=0; open_pr=0; max_turns=80; max_attempts=6; model=""; dry=0; engine=claude
plans=()
while [ $# -gt 0 ]; do
  case "$1" in
    --status) status_f=$2; shift 2 ;;
    --effort) effort_f=$2; shift 2 ;;
    --max) max_n=$2; shift 2 ;;
    --pr) open_pr=1; shift ;;
    --max-turns) max_turns=$2; shift 2 ;;
    --max-attempts) max_attempts=$2; shift 2 ;;
    --model) model=$2; shift 2 ;;
    --engine) engine=$2; shift 2 ;;
    --dry-run) dry=1; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    --*) echo "unknown option $1" >&2; exit 1 ;;
    *) plans+=("$1"); shift ;;
  esac
done

if [ ${#plans[@]} -eq 0 ]; then
  for f in docs/plans/*.md; do
    [ "$(basename "$f")" = README.md ] && continue
    s=$(grep -m1 '^status:' "$f" | sed -E 's/^status:[[:space:]]*//')
    e=$(grep -m1 '^effort:' "$f" | sed -E 's/^effort:[[:space:]]*//')
    [ "$s" = "$status_f" ] && [ "$e" = "$effort_f" ] && plans+=("$(basename "$f" .md)")
  done
fi
[ ${#plans[@]} -gt 0 ] || { echo "plan_runner: no plans selected (status=$status_f effort=$effort_f)"; exit 0; }
[ "$max_n" -gt 0 ] && plans=("${plans[@]:0:$max_n}")

echo "plan_runner: ${#plans[@]} plan(s): ${plans[*]}"
[ "$dry" = 1 ] && { echo "(dry run) worktrees under $wt_root, logs under $log_root"; exit 0; }

# Prompt = the /implement-plan command body with $ARGUMENTS expanded
prompt_tpl=$(awk 'BEGIN{fm=0} /^---$/{fm++; next} fm>=2{print}' .claude/commands/implement-plan.md)

allowed='Read,Edit,Write,MultiEdit,Glob,Grep,Agent,Bash(uv *),Bash(./scripts/*),Bash(scripts/*),Bash(git add *),Bash(git commit *),Bash(git diff *),Bash(git log *),Bash(git status *),Bash(git show *),Bash(git ls-files *),Bash(git merge-base *),Bash(git rev-parse *),Bash(grep *),Bash(test *),Bash(cat *),Bash(ls *),Bash(jq *),Bash(python *),Bash(python3 *)'

summary=()
for id in "${plans[@]}"; do
  plan="docs/plans/$id.md"
  [ -f "$plan" ] || { summary+=("$id: MISSING plan file"); continue; }
  wt="$wt_root/$id"
  echo; echo "══ $id ══"
  if [ ! -d "$wt" ]; then
    if git show-ref --verify --quiet "refs/heads/plan/$id"; then
      git worktree add "$wt" "plan/$id"
    else
      git worktree add -b "plan/$id" "$wt" main
    fi
  fi
  (
    cd "$wt"
    mkdir -p .claude/state
    uv sync --group dev >/dev/null
    scripts/plan_goal.sh start "$id" --max-attempts "$max_attempts"
    prompt=${prompt_tpl//\$ARGUMENTS/$id}
    args=(-p "$prompt" --permission-mode dontAsk --allowedTools "$allowed" --max-turns "$max_turns" --output-format json)
    [ -n "$model" ] && args+=(--model "$model")
    if [ "$engine" = cursor ]; then
      # Cursor CLI has no Stop hook: emulate the gate with a Ralph-style loop —
      # run the agent, judge with plan_goal.sh check, feed the verdict back, repeat.
      bin=$(command -v agent 2>/dev/null || command -v cursor-agent 2>/dev/null || true)
      [ -n "$bin" ] || { echo "plan_runner: Cursor CLI (agent / cursor-agent) not found" >&2; exit 1; }
      feedback=""
      for ((i=1; i<=max_attempts; i++)); do
        echo "plan_runner: cursor agent -p … (round $i/$max_attempts)"
        # flags per `agent --help`; --force = apply edits without confirmation
        "$bin" -p "$prompt"$'\n\n'"$feedback" ${model:+--model "$model"} --force --output-format text \
          > "$log_root/$id.cursor-$i.txt" 2>&1 || true
        if verdict=$(scripts/plan_goal.sh check 2>/dev/null); then
          echo done > .claude/state/result; break
        fi
        feedback="Previous round did not pass the DoD gate. Fix exactly this, then stop:"$'\n'"$verdict"
        [ "$(cat .claude/state/result 2>/dev/null)" = blocked ] && break
        [ "$i" -eq "$max_attempts" ] && echo exhausted > .claude/state/result
      done
      printf '{"engine":"cursor","rounds":%s}' "$i" > "$log_root/$id.json"
    else
      echo "plan_runner: claude -p … (max-turns $max_turns, gate attempts $max_attempts)"
      env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT claude "${args[@]}" > "$log_root/$id.json" || true
    fi
  )
  result=$(cat "$wt/.claude/state/result" 2>/dev/null || echo "no-result")
  turns=$(jq -r '.num_turns // "?"' "$log_root/$id.json" 2>/dev/null || echo "?")
  cost=$(jq -r '.total_cost_usd // "?"' "$log_root/$id.json" 2>/dev/null || echo "?")
  line="$id: $result (turns $turns, cost \$$cost, worktree $wt)"
  if [ "$result" = "done" ] && [ "$open_pr" = 1 ]; then
    title=$(grep -m1 '^title:' "$plan" | sed -E 's/^title:[[:space:]]*//')
    body=$(printf 'Implements plan [`%s`](docs/plans/%s.md) — goal mode run.\n\n## Acceptance criteria / verify.sh (tail)\n```\n%s\n```\n\n## Review\n```\n%s\n```\n\nManual criteria (if any) are left for the owner.\n' \
      "$id" "$id" "$(tail -n 40 "$wt/.claude/state/verify-last.log" 2>/dev/null || echo 'see logs')" \
      "$(jq -r '.verdict + " by " + (.reviewers|join(", "))' "$wt/.claude/state/review-verdict.json" 2>/dev/null || echo 'n/a')")
    (cd "$wt" && git push -u origin "plan/$id" && gh pr create --base main --head "plan/$id" --title "$title" --body "$body") \
      && line="$line → PR opened" || line="$line → push/PR FAILED"
  elif [ "$result" = "done" ]; then
    line="$line → ready: cd $wt && git push -u origin plan/$id && gh pr create --base main --head plan/$id"
  fi
  summary+=("$line")
done

echo; echo "══ summary ══"; printf '%s\n' "${summary[@]}"
echo "worktrees: git worktree list   |   clean up: git worktree remove <path>"
