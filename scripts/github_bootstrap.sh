#!/usr/bin/env bash
# One-time GitHub setup for the Kaleta release cycle: labels + milestones.
# Requires: gh CLI authenticated as the repo owner (gh auth login).
# Safe to re-run — labels are upserted, existing milestones are skipped.

set -euo pipefail

REPO="DawidAdamski/kaleta"

command -v gh >/dev/null || { echo "gh CLI not found — https://cli.github.com"; exit 1; }
gh auth status >/dev/null || { echo "Not authenticated — run: gh auth login"; exit 1; }

echo "==> Labels"
# Type labels (issue templates already apply 'bug' and 'enhancement').
gh label create "bug"           --repo "$REPO" --force --color d73a4a --description "Something is broken"
gh label create "enhancement"   --repo "$REPO" --force --color a2eeef --description "New feature or improvement"
gh label create "documentation" --repo "$REPO" --force --color 0075ca --description "Docs, guides, ADRs"
gh label create "good first issue" --repo "$REPO" --force --color 7057ff --description "Small, well-scoped, no deep context needed"
gh label create "help wanted"   --repo "$REPO" --force --color 008672 --description "Contributions welcome"

# Process labels.
gh label create "needs-triage"  --repo "$REPO" --force --color ededed --description "Awaiting review by the maintainer"
gh label create "blocked"       --repo "$REPO" --force --color b60205 --description "Waiting on another issue or a decision"
gh label create "spec:planned"  --repo "$REPO" --force --color c5def5 --description "Backed by a @planned scenario in docs/bdd.md"

# Area labels — match the workflow structure of docs/bdd.md.
gh label create "area:setup"         --repo "$REPO" --force --color fbca04 --description "Wizard, institutions, accounts, categories, tags, payees"
gh label create "area:transactions"  --repo "$REPO" --force --color fbca04 --description "Entry, splits, quick entry, pagination"
gh label create "area:import"        --repo "$REPO" --force --color fbca04 --description "CSV import, transfer recognition, auto-categorisation"
gh label create "area:budgets"       --repo "$REPO" --force --color fbca04 --description "Category budgets, monthly readiness, comparisons"
gh label create "area:recurring"     --repo "$REPO" --force --color fbca04 --description "Planned transactions, detection, subscriptions"
gh label create "area:funds"         --repo "$REPO" --force --color fbca04 --description "Skarbonki, irregular fund, reserves, gifts"
gh label create "area:insight"       --repo "$REPO" --force --color fbca04 --description "Forecast, credit, debts, investments, AI"
gh label create "area:api"           --repo "$REPO" --force --color fbca04 --description "REST API, tokens, automation"
gh label create "area:ui"            --repo "$REPO" --force --color fbca04 --description "Dashboard, layout, theming, i18n"
gh label create "area:infra"         --repo "$REPO" --force --color fbca04 --description "CI, packaging, Docker, auth, data safety"

echo "==> Milestones"
create_milestone() {
  local title="$1" due="$2" desc="$3"
  if gh api "repos/$REPO/milestones?state=all" --paginate -q '.[].title' | grep -Fxq "$title"; then
    echo "    exists: $title"
  else
    if [ -n "$due" ]; then
      gh api "repos/$REPO/milestones" -f title="$title" -f due_on="${due}T23:59:59Z" -f description="$desc" >/dev/null
    else
      gh api "repos/$REPO/milestones" -f title="$title" -f description="$desc" >/dev/null
    fi
    echo "    created: $title"
  fi
}

create_milestone "v0.1.0 — Open-source launch" "2026-08-31" \
"A stranger can find, install, trust, and contribute to Kaleta. Public-repo readiness, zero-config bootstrap, English-first audit, hosted demo. Roadmap: Q4 §2–3."

create_milestone "v0.2.0 — Workflow polish" "2026-10-31" \
"Deferred Q4 drafts: payee identities automerge, transactions QoL (notes, payee autocomplete, upcoming planned), import per-file mapping memory, dashboard polish, wizard reminders, budgets plan unification. Roadmap: Q4 §4."

create_milestone "v0.3.0 — Capture without friction" "2026-12-31" \
"First slice of @planned scenarios from docs/bdd.md: transaction splits (KAL-SPL), transfer recognition (KAL-TRF), quick entry (KAL-QIK), auto-categorisation rules (KAL-RUL)."

create_milestone "Backlog" "" \
"Unscheduled @planned features from docs/bdd.md: funds & goals, irregular fund, gifts, debts, subscriptions, investments, comparisons, AI insights, public API."

echo
echo "==> Done. Manual steps (GitHub web UI):"
echo "  1. Settings → General → Features: make sure 'Issues' is enabled."
echo "  2. Settings → Moderation options → Interaction limits: ensure no limit"
echo "     blocks issue creation — logged-out view currently shows"
echo "     'Issue creation is restricted in this repository'."
echo "  3. Optional: create a 'Kaleta roadmap' Project board and add milestones."
