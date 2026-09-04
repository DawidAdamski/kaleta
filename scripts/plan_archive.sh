#!/usr/bin/env bash
# Archive an implemented plan — the deterministic version of the plan-archiver subagent.
#
#   scripts/plan_archive.sh <plan_id> (--pr N | --sha SHA[,SHA...]) [--fast] [--no-commit]
#
#   --pr N        resolve the merge commit via `gh pr view N` (needs gh auth)
#   --sha ...     explicit commit(s) on main that implemented the plan
#   --fast        skip re-running the acceptance criteria (use when PR CI already ran them)
#   --no-commit   leave the changes staged, do not create the commit
#
# Steps (same as docs/plans/README.md § "Archiving a plan"):
#   verify commits → touchpoint overlap → acceptance criteria → append ## Implementation
#   → status: archived (+ archived_at) → git mv to archive/ → README index row → commit
# Idempotent: exits 0 without changes when the plan is already archived.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

plan_id=${1:?usage: plan_archive.sh <plan_id> (--pr N | --sha SHA) [--fast] [--no-commit]}; shift
pr=""; shas=""; fast=0; commit=1
while [ $# -gt 0 ]; do
  case "$1" in
    --pr) pr=$2; shift 2 ;;
    --sha) shas=$2; shift 2 ;;
    --fast) fast=1; shift ;;
    --no-commit) commit=0; shift ;;
    *) echo "plan_archive: unknown option $1" >&2; exit 1 ;;
  esac
done

plan="docs/plans/$plan_id.md"
if [ ! -f "$plan" ] && [ -f "docs/plans/archive/$plan_id.md" ]; then
  echo "plan_archive: $plan_id is already archived — nothing to do"; exit 0
fi
[ -f "$plan" ] || { echo "plan_archive: $plan not found" >&2; exit 1; }

# ── resolve commits ──────────────────────────────────────────────────────
if [ -n "$pr" ] && [ -z "$shas" ]; then
  command -v gh >/dev/null || { echo "plan_archive: gh not installed; pass --sha" >&2; exit 1; }
  shas=$(gh pr view "$pr" --json mergeCommit --jq '.mergeCommit.oid')
  [ -n "$shas" ] && [ "$shas" != null ] || { echo "plan_archive: PR #$pr has no merge commit (not merged?)" >&2; exit 1; }
fi
[ -n "$shas" ] || { echo "plan_archive: pass --pr N or --sha SHA" >&2; exit 1; }
IFS=, read -r -a sha_list <<< "$shas"
for s in "${sha_list[@]}"; do
  git cat-file -e "$s^{commit}" 2>/dev/null || { echo "plan_archive: commit $s not found (git fetch?)" >&2; exit 1; }
done

# ── touchpoint overlap (warn only) ───────────────────────────────────────
changed=$(for s in "${sha_list[@]}"; do
  if [ "$(git rev-list --parents -n1 "$s" | wc -w)" -gt 2 ]; then git diff --name-only "$s^1" "$s"; else git show --name-only --format= "$s"; fi
done | sort -u)
touch_hits=0
while IFS= read -r line; do
  path=$(printf '%s' "$line" | sed -nE 's/^- *`([^`]+)`.*/\1/p'); [ -n "$path" ] || continue
  if printf '%s\n' "$changed" | grep -qF -- "$path" || printf '%s\n' "$changed" | grep -qF -- "$(dirname "$path")/"; then touch_hits=$((touch_hits+1)); fi
done < <(awk '/^## Touchpoints/{f=1;next} /^## /{f=0} f' "$plan")
notes=""
[ "$touch_hits" -eq 0 ] && notes="Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA."

# ── acceptance criteria ──────────────────────────────────────────────────
crit_rows=""
if [ "$fast" = 1 ]; then
  crit_rows="| _(skipped: --fast, validated by PR CI)_ | – |"$'\n'
else
  while IFS= read -r cmd; do
    [ -z "$cmd" ] && continue
    case "$cmd" in \[manual\]*|\[blocked\]*) continue ;; esac
    if bash -c "$cmd" >/dev/null 2>&1; then rc=0; else rc=$?; fi
    crit_rows="$crit_rows| \`$cmd\` | $rc |"$'\n'
    [ "$rc" -eq 0 ] || { echo "plan_archive: acceptance criterion failed (exit $rc): $cmd — not archiving" >&2; exit 1; }
  done < <(awk '/^## Acceptance criteria/{f=1;next} /^## /{f=0} f' "$plan" | grep -E '^- `' | sed -E 's/^- `([^`]*)`.*/\1/')
fi

# ── BDD retag check (warn only) ──────────────────────────────────────────
planned=$(grep -oE 'KAL-[A-Z]{3,4}-[0-9]{3}' "$plan" | sort -u | while read -r id; do
  grep -qE "^[[:space:]]*$id[[:space:]]+@planned" docs/bdd.md && echo "$id" || true; done)
[ -n "$planned" ] && notes="$notes${notes:+ }Still @planned in docs/bdd.md: $(echo "$planned" | tr '\n' ' ')— retag before or after archiving."

# ── append ## Implementation ─────────────────────────────────────────────
today=$(date +%Y-%m-%d)
{
  printf '\n## Implementation\n\nLanded on %s%s.\n\n| SHA | Author | Date | Message |\n|---|---|---|---|\n' "$today" "${pr:+ (PR #$pr)}"
  for s in "${sha_list[@]}"; do git show -s --format='| `%h` | %an | %ad | %s |' --date=short "$s"; done
  printf '\n**Files changed:**\n'; printf '%s\n' "$changed" | sed 's/^/- /'
  printf '\n**Acceptance criteria run:**\n\n| Command | Exit |\n|---|---|\n%s' "$crit_rows"
  [ -n "$notes" ] && printf '\n**Notes:** %s\n' "$notes"
} >> "$plan"

# ── frontmatter ──────────────────────────────────────────────────────────
python3 - "$plan" "$today" <<'PY'
import re,sys
p,today=sys.argv[1],sys.argv[2]; s=open(p).read()
s=re.sub(r'^status:.*$', f'status: archived\narchived_at: {today}', s, count=1, flags=re.M)
open(p,'w').write(s)
PY

# ── relative links: the file moves one directory down ────────────────────
python3 - "$plan" <<'PY2'
import re,os,sys
p=sys.argv[1]; s=open(p).read()
s=re.sub(r'^(roadmap_ref:\s*)\.\./', r'\1../../', s, count=1, flags=re.M)
def fix(m):
    label,target=m.group(1),m.group(2)
    if target.startswith(('http://','https://','mailto:','#')): return m.group(0)
    if target.startswith('archive/'): return f'[{label}]({target[len("archive/"):]})'
    if target.startswith('../'): return f'[{label}](../{target})'
    if '/' not in target.split('#')[0]:
        base=target.split('#')[0]
        if os.path.exists(os.path.join('docs/plans/archive', base)): return m.group(0)
        if os.path.exists(os.path.join('docs/plans', base)): return f'[{label}](../{target})'
    return m.group(0)
s=re.sub(r'(?<!!)\[([^\]]*)\]\(([^)]+)\)', fix, s)
open(p,'w').write(s)
PY2

# ── move + index ─────────────────────────────────────────────────────────
git mv "$plan" "docs/plans/archive/$plan_id.md"
python3 - "$plan_id" <<'PY'
import sys; pid=sys.argv[1]; p='docs/plans/README.md'
lines=open(p).read().split('\n'); hit=False
for i,l in enumerate(lines):
    if f'[{pid}](' not in l or not l.startswith('|'): continue
    cells=l.split('|')
    for j,c in enumerate(cells):
        if f'[{pid}](' in c:
            cells[j]=c.replace(f'({pid}.md)', f'(archive/{pid}.md)')
            if j+1 < len(cells)-1: cells[j+1]=' archived '
            hit=True; break
    lines[i]='|'.join(cells)
open(p,'w').write('\n'.join(lines))
print('plan_archive: README index row updated' if hit else 'plan_archive: WARNING no index row found in docs/plans/README.md')
PY

# ── inbound links: every doc that pointed at the plan's old location ──────
# The block above fixes links *inside* the moved plan. This one fixes links
# *at* it from anywhere else — without it, an already-archived plan that
# references a sibling draft (see archive/import-bank-profiles.md) dangles
# the moment that draft is archived, and check_doc_links.py goes red.
# Prints one repointed path per line; notices go to stderr so they do not
# pollute the captured list.
inbound=$(python3 - "$plan_id" <<'PY3'
import os, re, sys

plan_id = sys.argv[1]
old_target = os.path.join("docs/plans", f"{plan_id}.md")
new_target = os.path.join("docs/plans/archive", f"{plan_id}.md")
link_re = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")
skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    for name in sorted(files):
        if not name.endswith(".md"):
            continue
        path = os.path.normpath(os.path.join(root, name))
        if path == new_target:
            continue  # the moved plan itself — already rewritten above
        with open(path, encoding="utf-8") as fh:
            original = fh.read()

        def repoint(match):
            label, target = match.group(1), match.group(2)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                return match.group(0)
            ref, _, anchor = target.partition("#")
            if not ref:
                return match.group(0)
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), ref))
            if resolved != old_target:
                return match.group(0)
            rel = os.path.relpath(new_target, os.path.dirname(path) or ".")
            return f"[{label}]({rel}{'#' + anchor if anchor else ''})"

        updated = link_re.sub(repoint, original)
        if updated != original:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(updated)
            print(path)
PY3
)
if [ -n "$inbound" ]; then
  printf '%s\n' "$inbound" | while IFS= read -r f; do [ -n "$f" ] && git add "$f"; done
  echo "plan_archive: repointed inbound links to $plan_id in:" >&2
  printf '  - %s\n' $inbound >&2
fi

git add "docs/plans/archive/$plan_id.md" docs/plans/README.md

if [ "$commit" = 1 ]; then
  git commit -q -m "docs(plans): archive $plan_id${pr:+ (#$pr)}" && echo "plan_archive: committed $(git rev-parse --short HEAD)"
else
  echo "plan_archive: staged (no commit)"
fi
[ -n "$notes" ] && echo "plan_archive: note — $notes" >&2
echo "plan_archive: $plan_id → docs/plans/archive/ (status: archived)"
