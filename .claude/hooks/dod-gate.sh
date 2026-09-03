#!/usr/bin/env bash
# Stop hook — deterministic Definition-of-Done judge for goal mode.
#
# Active only while .claude/state/active-plan exists (set by scripts/plan_goal.sh start).
# Otherwise it exits 0 and Claude Code behaves normally.
#
# Verdict "not done" is returned as {"decision":"block","reason":...} on stdout,
# which makes Claude keep working with the reason as feedback. Bounded by
# .claude/state/max-attempts (default 6); after that the session is allowed to
# stop and .claude/state/result is set to "exhausted".
set -uo pipefail

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root" || exit 0
state=.claude/state
input=$(cat)   # hook payload (unused beyond presence)

[ -f "$state/active-plan" ] || exit 0
plan_id=$(cat "$state/active-plan")
plan="docs/plans/$plan_id.md"

# Explicit escape hatch: scripts/plan_goal.sh block "<reason>"
if [ "$(cat "$state/result" 2>/dev/null)" = "blocked" ]; then exit 0; fi

max=$(cat "$state/max-attempts" 2>/dev/null || echo 6)
attempt=$(( $(cat "$state/attempts" 2>/dev/null || echo 0) + 1 ))
# DOD_GATE_DRY=1 (scripts/plan_goal.sh check): report only, do not count an attempt
[ "${DOD_GATE_DRY:-0}" = 1 ] || echo "$attempt" > "$state/attempts"

fail=(); warn=()
add()  { fail+=("$1"); }
note() { warn+=("$1"); }

[ -f "$plan" ] || { echo "dod-gate: plan $plan missing, gate disabled" >&2; exit 0; }

base=$(git merge-base HEAD main 2>/dev/null || echo main)

# ── 0. plan hygiene (Working Agreement 1, 7) ─────────────────────────────
grep -q '^status: in-progress' "$plan" || add "Plan frontmatter must say 'status: in-progress' while work is ongoing ($plan)."
grep -q '_Filled in as work progresses._' "$plan" && add "Fill in '## Implementation notes' in $plan with decisions and resolved open questions (rule 7)."

# ── 1. green-washing detector (rules 4, 6, 10) — added lines only ────────
added=$(git diff "$base" -- . ':(exclude)docs/**' | grep '^+' | grep -v '^+++' || true)
printf '%s\n' "$added" | grep -qE 'pytest\.mark\.(skip|xfail)|pytest\.skip\(|@unittest\.skip' \
  && add "New skip/xfail in the diff — forbidden (rule 4). Fix the root cause instead."
printf '%s\n' "$added" | grep -qE '^\+[[:space:]]*ignore_imports' \
  && add "New ignore_imports entry — forbidden (rule 6). The import-linter contract is law."
printf '%s\n' "$added" | grep -qE '#[[:space:]]*type:[[:space:]]*ignore' \
  && note "New '# type: ignore' in the diff — justify it in Implementation notes or remove (rule 10)."
git diff "$base" -- tests | grep -qE '^-[[:space:]]*assert' \
  && note "Assertions were removed from existing tests — make sure this is explained in Implementation notes (rule 4)."

# ── 2. executable acceptance criteria from the plan ──────────────────────
crit=$(awk '/^## Acceptance criteria/{f=1;next} /^## /{f=0} f' "$plan" | grep -E '^- `' | sed -E 's/^- `([^`]*)`.*/\1/')
ncrit=0
while IFS= read -r cmd; do
  [ -z "$cmd" ] && continue
  case "$cmd" in \[manual\]*) continue ;; esac
  ncrit=$((ncrit+1))
  out=$(bash -c "$cmd" 2>&1) || add "Acceptance criterion failed: \`$cmd\`"$'\n'"$(printf '%s' "$out" | tail -n 15)"
done <<< "$crit"
nmanual=$(awk '/^## Acceptance criteria/{f=1;next} /^## /{f=0} f' "$plan" | grep -cE '^- `?\[manual\]' || true)
[ "$ncrit" -eq 0 ] && note "Plan has no executable acceptance criteria (backtick commands) — the gate relies on verify.sh and the reviewer only."

# ── 3. Definition-of-Done gate (rule 2, 8) ───────────────────────────────
e2e=""
git diff --quiet "$base" -- src/kaleta/views/ 2>/dev/null || e2e="--e2e"
out=$(./scripts/verify.sh $e2e 2>&1); rc=$?
printf '%s\n' "$out" > "$state/verify-last.log"
[ $rc -eq 0 ] || add "./scripts/verify.sh $e2e failed:"$'\n'"$(printf '%s' "$out" | tail -n 40)"

# ── 4. independent review verdict (scripts/review_gate.sh) ───────────────
verdict_file="$state/review-verdict.json"
diff_hash=$(git diff "$base" | { command -v sha256sum >/dev/null 2>&1 && sha256sum || shasum -a 256; } | cut -c1-16)
if [ ! -f "$verdict_file" ]; then
  add "No review verdict yet. Run ./scripts/review_gate.sh (independent reviewer) and fix its findings."
else
  v=$(jq -r '.verdict' "$verdict_file"); h=$(jq -r '.diff_hash' "$verdict_file")
  if [ "$h" != "$diff_hash" ]; then
    add "Review verdict is stale — the diff changed since the review. Run ./scripts/review_gate.sh again."
  elif [ "$v" != "approve" ]; then
    add "Reviewer requested changes:"$'\n'"$(jq -r '.findings[]? | "  - [\(.reviewer // "claude")] \(.file):\(.line // "?") — \(.summary)"' "$verdict_file")"
  fi
fi

# ── verdict ──────────────────────────────────────────────────────────────
if [ ${#fail[@]} -eq 0 ]; then
  echo done > "$state/result"
  rm -f "$state/attempts"
  { echo "dod-gate: DONE for plan $plan_id (manual criteria left for the owner: $nmanual)";
    [ ${#warn[@]} -gt 0 ] && printf 'warning: %s\n' "${warn[@]}"; } >&2
  exit 0
fi

if [ "${DOD_GATE_DRY:-0}" != 1 ] && [ "$attempt" -ge "$max" ]; then
  echo exhausted > "$state/result"
  { echo "dod-gate: $attempt/$max attempts exhausted — letting the session stop. Open failures:";
    printf -- '- %s\n' "${fail[@]}"; } >&2
  exit 0
fi

reason=$(
  printf 'DoD gate — attempt %s/%s — NOT done yet. Fix everything below, then finish your turn again.\n\n' "$attempt" "$max"
  printf -- '- %s\n\n' "${fail[@]}"
  [ ${#warn[@]} -gt 0 ] && { printf 'Warnings (not blocking, but address or justify):\n'; printf -- '- %s\n' "${warn[@]}"; }
  printf '\nRules: do not ask questions — resolve open questions with the plan defaults and record them in Implementation notes. If you are truly blocked, run: scripts/plan_goal.sh block "<reason>".\n'
)
jq -n --arg r "$reason" '{decision:"block", reason:$r}'
