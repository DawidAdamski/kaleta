#!/usr/bin/env bash
# Independent review of the current branch against its plan.
#
# Spawns a fresh, read-only `claude -p` reviewer (a separate context that did
# not write the code) and — optionally — a second reviewer from a different
# model family via the Cursor CLI. Writes .claude/state/review-verdict.json,
# which the Stop hook (.claude/hooks/dod-gate.sh) requires to be "approve"
# and to match the current diff.
#
#   scripts/review_gate.sh [plan_id]
#
# Env:
#   KALETA_REVIEW_MODEL        model for the Claude reviewer   (default: sonnet)
#   KALETA_CROSS_REVIEW=1      also run the Cursor CLI reviewer (needs `agent` / `cursor-agent`)
#   KALETA_CROSS_REVIEW_MODEL  Cursor model id                 (default: gpt-5)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
state=.claude/state; mkdir -p "$state"

plan_id=${1:-$(cat "$state/active-plan" 2>/dev/null || true)}
[ -n "$plan_id" ] || { echo "usage: review_gate.sh <plan_id> (or arm a plan with scripts/plan_goal.sh start)" >&2; exit 1; }
plan="docs/plans/$plan_id.md"
[ -f "$plan" ] || { echo "review_gate: $plan not found" >&2; exit 1; }

base=$(git merge-base HEAD main)
diff_hash=$(git diff "$base" | { command -v sha256sum >/dev/null 2>&1 && sha256sum || shasum -a 256; } | cut -c1-16)
if git diff --quiet "$base"; then echo "review_gate: no diff against $base — nothing to review" >&2; exit 1; fi

schema='{"type":"object","properties":{"verdict":{"type":"string","enum":["approve","changes"]},"findings":{"type":"array","items":{"type":"object","properties":{"file":{"type":"string"},"line":{"type":"integer"},"section":{"type":"string"},"summary":{"type":"string"}},"required":["file","summary"]}}},"required":["verdict","findings"]}'

read -r -d '' prompt <<PROMPT || true
You are the independent code reviewer for this repository. You did NOT write
this code — review it adversarially but fairly. Do not edit anything.

Scope of review: the working-tree diff against merge-base $base.
Get it with: git diff $base   (and git diff $base --stat)

Process:
1. Read docs/review-checklist.md — it is your rubric.
2. Read the plan docs/plans/$plan_id.md: Scope, "Not in scope",
   Acceptance criteria, Implementation notes.
3. Read the Working Agreement in AGENTS.md.
4. Review the diff against the checklist. You may run
   `uv run pytest <path> -q` to check a claim.
5. Hard rules → verdict "changes": diff exceeds plan scope without
   justification; new skip/xfail; new ignore_imports; type erosion
   (Any for a real type, enum→str); business logic hiding in views/;
   new user-facing behaviour without a KAL- scenario in docs/bdd.md;
   Implementation notes not updated.
6. Do not comment on style that ruff/mypy already enforce.

Return ONLY a JSON object: {"verdict":"approve"|"changes","findings":[{"file","line","section","summary"}]}.
"approve" means you would merge as-is. Include findings even when approving (as nits) but keep them specific: file, line, what and why.
PROMPT

echo "review_gate: Claude reviewer (${KALETA_REVIEW_MODEL:-sonnet}) on diff $diff_hash …" >&2
env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT claude -p "$prompt" \
  --model "${KALETA_REVIEW_MODEL:-sonnet}" \
  --permission-mode dontAsk \
  --allowedTools "Read,Grep,Glob,Bash(git diff *),Bash(git log *),Bash(git show *),Bash(git status *),Bash(uv run pytest *)" \
  --max-turns 30 \
  --output-format json \
  --json-schema "$schema" > "$state/review-raw.json" || true

claude_verdict=$(jq -c '.structured_output // (.result | try fromjson catch empty) // empty' "$state/review-raw.json" 2>/dev/null || true)
if [ -z "$claude_verdict" ]; then
  # last resort: pull the first {...} block out of the text result
  claude_verdict=$(jq -r '.result // empty' "$state/review-raw.json" | python3 -c '
import sys,re,json
t=sys.stdin.read(); m=re.search(r"\{.*\}", t, re.S)
print(json.dumps(json.loads(m.group(0))) if m else "")' 2>/dev/null || true)
fi
[ -n "$claude_verdict" ] || { echo "review_gate: could not parse the Claude reviewer output (see $state/review-raw.json)" >&2; exit 1; }
claude_verdict=$(printf '%s' "$claude_verdict" | jq -c '.findings = [(.findings // [])[] | . + {reviewer:"claude"}]')
reviewers='["claude"]'
merged="$claude_verdict"

if [ "${KALETA_CROSS_REVIEW:-0}" = "1" ]; then
  bin=$(command -v agent 2>/dev/null || command -v cursor-agent 2>/dev/null || true)
  if [ -z "$bin" ]; then
    echo "review_gate: KALETA_CROSS_REVIEW=1 but Cursor CLI (agent / cursor-agent) not found — skipping" >&2
  else
    model=${KALETA_CROSS_REVIEW_MODEL:-gpt-5}
    echo "review_gate: Cursor CLI reviewer ($model) …" >&2
    # Cursor CLI flags may differ by version — check `agent --help` if this fails.
    "$bin" -p "$prompt" --model "$model" --output-format text > "$state/review-cross-raw.txt" 2>/dev/null || true
    cross=$(python3 -c '
import sys,re,json
t=open(sys.argv[1]).read(); m=re.search(r"\{.*\}", t, re.S)
print(json.dumps(json.loads(m.group(0))) if m else "")' "$state/review-cross-raw.txt" 2>/dev/null || true)
    if [ -n "$cross" ]; then
      cross=$(printf '%s' "$cross" | jq -c --arg r "cursor:$model" '.findings = [(.findings // [])[] | . + {reviewer:$r}]')
      merged=$(jq -n -c --argjson a "$merged" --argjson b "$cross" \
        '{verdict: (if ($a.verdict=="approve" and $b.verdict=="approve") then "approve" else "changes" end),
          findings: ($a.findings + $b.findings)}')
      reviewers="[\"claude\",\"cursor:$model\"]"
    else
      echo "review_gate: could not parse the Cursor reviewer output (see $state/review-cross-raw.txt) — ignoring it" >&2
    fi
  fi
fi

jq -n -c --arg plan "$plan_id" --arg h "$diff_hash" --argjson v "$merged" --argjson r "$reviewers" \
  --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{plan_id:$plan, diff_hash:$h, at:$at, reviewers:$r, verdict:$v.verdict, findings:$v.findings}' > "$state/review-verdict.json"

echo "review_gate: verdict = $(jq -r .verdict "$state/review-verdict.json") (reviewers: $(jq -r '.reviewers|join(", ")' "$state/review-verdict.json"), diff $diff_hash)"
jq -r '.findings[] | "  - [\(.reviewer)] \(.file):\(.line // "?") [\(.section // "-")] \(.summary)"' "$state/review-verdict.json"
[ "$(jq -r .verdict "$state/review-verdict.json")" = "approve" ]
