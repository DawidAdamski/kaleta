#!/usr/bin/env bash
# Create one GitHub issue per @planned feature in docs/bdd.md.
# Requires: gh CLI authenticated as the repo owner; labels + milestones
# from scripts/github_bootstrap.sh must exist.
# Safe to re-run — issues whose exact title already exists are skipped.

set -euo pipefail

REPO="DawidAdamski/kaleta"
SPEC="https://github.com/$REPO/blob/main/docs/bdd.md"

command -v gh >/dev/null || { echo "gh CLI not found — https://cli.github.com"; exit 1; }
gh auth status >/dev/null || { echo "Not authenticated — run: gh auth login"; exit 1; }

EXISTING="$(gh issue list --repo "$REPO" --state all --limit 500 --json title -q '.[].title')"

create_issue() {
  local title="$1" milestone="$2" labels="$3" body="$4"
  if grep -Fxq "$title" <<<"$EXISTING"; then
    echo "    exists: $title"
    return
  fi
  gh issue create --repo "$REPO" --title "$title" --milestone "$milestone" \
    --label "$labels" --body "$body" >/dev/null
  echo "    created: $title"
}

DOD="**Definition of done:** feature implemented, scenarios retagged \`@planned\` → \`@automated\`/\`@manual\` in \`docs/bdd.md\`, tests reference the KAL-* IDs in their \`Covers:\` docstring, \`scripts/spec_coverage.py\` green."

echo "==> Issues from @planned features"

create_issue "Payee identities: detect and merge similar payee names (KAL-PID)" \
  "v0.2.0 — Workflow polish" "enhancement,spec:planned,area:setup" \
"The same institution appears under many spellings in bank exports, so per-payee spending totals lie. Detect similar payees, suggest merges, and report top payees.

**Spec:** [$SPEC#feature-payee-identities]($SPEC#feature-payee-identities)

- [ ] KAL-PID-001 System suggests merging similarly named payees
- [ ] KAL-PID-002 Accepting a merge suggestion rewrites history
- [ ] KAL-PID-003 Top payees report

$DOD"

create_issue "Quick entry: keyboard-first, low-friction transaction entry (KAL-QIK)" \
  "v0.3.0 — Capture without friction" "enhancement,spec:planned,area:transactions" \
"Consistency is the hard part of tracking finances. Entering a daily/weekly/monthly batch by hand must work without touching the mouse.

**Spec:** [$SPEC#feature-quick-entry]($SPEC#feature-quick-entry)

- [ ] KAL-QIK-001 Add an expense using the keyboard only
- [ ] KAL-QIK-002 Quick entry remembers the previous context
- [ ] KAL-QIK-003 Batch entry keeps the form open

$DOD"

create_issue "Transaction splits: divide one transaction across categories (KAL-SPL)" \
  "v0.3.0 — Capture without friction" "enhancement,spec:planned,area:transactions" \
"A single receipt (\"Lidl 214,50\") often spans categories tracked separately (groceries vs alcohol). Splits must be fast and feed category reports.

**Spec:** [$SPEC#feature-transaction-splits]($SPEC#feature-transaction-splits)

- [ ] KAL-SPL-001 Split an expense into two categories
- [ ] KAL-SPL-002 Split lines must sum to the original amount
- [ ] KAL-SPL-003 Split lines feed category reports
- [ ] KAL-SPL-004 Edit an existing split

$DOD"

create_issue "Transfer recognition: pair own-account transfers from imports (KAL-TRF)" \
  "v0.3.0 — Capture without friction" "enhancement,spec:planned,area:import" \
"Bank CSV exports show a transfer between own accounts as an expense on one side and income on the other, corrupting totals. Suggest pairs automatically, allow manual pairing, exclude pairs from totals.

**Spec:** [$SPEC#feature-transfer-recognition]($SPEC#feature-transfer-recognition)

- [ ] KAL-TRF-001 Manually pair two imported rows as a transfer
- [ ] KAL-TRF-002 Import suggests transfer pairs across accounts
- [ ] KAL-TRF-003 Recognised transfers are excluded from totals

$DOD"

create_issue "Auto-categorisation rules: Lidl means groceries by default (KAL-RUL)" \
  "v0.3.0 — Capture without friction" "enhancement,spec:planned,area:import" \
"Recurring merchants should not need recurring clicks: rules map descriptions/payees to categories, apply at import, and get suggested from repeated manual categorisation.

**Spec:** [$SPEC#feature-auto-categorisation-rules]($SPEC#feature-auto-categorisation-rules)

- [ ] KAL-RUL-001 Create a categorisation rule
- [ ] KAL-RUL-002 Rules apply during CSV import
- [ ] KAL-RUL-003 Suggest a rule from repeated manual categorisation
- [ ] KAL-RUL-004 Manual category always wins over a rule

$DOD"

create_issue "Budget planning comparisons: plan next month against history (KAL-CMP)" \
  "Backlog" "enhancement,spec:planned,area:budgets" \
"Planning next month should lean on evidence: last month's actuals and the same month in previous years, side by side.

**Spec:** [$SPEC#feature-budget-planning-comparisons]($SPEC#feature-budget-planning-comparisons)

- [ ] KAL-CMP-001 Planning view shows previous month actuals side by side
- [ ] KAL-CMP-002 Planning view shows the same month in previous years
- [ ] KAL-CMP-003 Start from last month's plan and adjust

$DOD"

create_issue "Recurring payment detection: turn history into planned transactions (KAL-REC)" \
  "Backlog" "enhancement,spec:planned,area:recurring" \
"Payments repeating with stable amount and cadence should be detected and convertible to planned transactions in one step — feeding the forecast and flagging price drift.

**Spec:** [$SPEC#feature-recurring-payment-detection]($SPEC#feature-recurring-payment-detection)

- [ ] KAL-REC-001 Detect a stable monthly payment
- [ ] KAL-REC-002 Convert a detection to a planned transaction
- [ ] KAL-REC-003 Link past transactions to the planned series
- [ ] KAL-REC-004 Amount drift is flagged

$DOD"

create_issue "Subscriptions panel: every subscription in one place (KAL-SUB)" \
  "Backlog" "enhancement,spec:planned,area:recurring" \
"One panel listing every subscription — what, how much, monthly or yearly — with a normalised monthly total, instead of reconstructing it from memory.

**Spec:** [$SPEC#feature-subscriptions-panel]($SPEC#feature-subscriptions-panel)

- [ ] KAL-SUB-001 Subscriptions are listed with cadence and price
- [ ] KAL-SUB-002 Panel shows the normalised monthly total
- [ ] KAL-SUB-003 Add a subscription from a detected recurring payment
- [ ] KAL-SUB-004 Mark a subscription as cancelled

$DOD"

create_issue "Annual review: plan the whole year in one sitting (KAL-ANR)" \
  "Backlog" "enhancement,spec:planned,area:budgets" \
"A guided yearly ritual: summarise the closing year per category, carry budgets forward with adjustments, decide on each subscription and irregular item.

**Spec:** [$SPEC#feature-annual-review]($SPEC#feature-annual-review)

- [ ] KAL-ANR-001 Annual review summarises the closing year
- [ ] KAL-ANR-002 Carry budgets into the next year with adjustments
- [ ] KAL-ANR-003 Review subscriptions and irregular items

$DOD"

create_issue "Irregular expenses fund: yearly costs divided by 10 (KAL-IRR)" \
  "Backlog" "enhancement,spec:planned,area:funds" \
"Yearly and surprise costs (car insurance, property tax, heating underpayment) paid from a dedicated fund. Each yearly item ÷ 10 — not 12 — because it is always more expensive, and the surplus covers rises and contingencies.

**Spec:** [$SPEC#feature-irregular-expenses-fund]($SPEC#feature-irregular-expenses-fund)

- [ ] KAL-IRR-001 Define an irregular yearly item
- [ ] KAL-IRR-002 Fund shows the total monthly contribution
- [ ] KAL-IRR-003 Monthly contribution is a planned transfer
- [ ] KAL-IRR-004 Pay an item from the fund
- [ ] KAL-IRR-005 Unplanned expense covered by the fund

$DOD"

create_issue "Gift planning: people, occasions, amounts feeding the irregular fund (KAL-GFT)" \
  "Backlog" "enhancement,spec:planned,area:funds" \
"A list of people and occasions with planned amounts; the yearly total feeds the irregular fund, so Christmas never raids December's budget.

**Spec:** [$SPEC#feature-gift-planning]($SPEC#feature-gift-planning)

- [ ] KAL-GFT-001 Maintain the gift list
- [ ] KAL-GFT-002 Gift total feeds the irregular fund
- [ ] KAL-GFT-003 Mark a gift as bought

$DOD"

create_issue "Savings goals (skarbonki): targets, progress, pace (KAL-GOL)" \
  "Backlog" "enhancement,spec:planned,area:funds" \
"The second budgeting dimension besides categories: piggy-bank goals with target amount and date, contributions, progress, and a pace hint.

**Spec:** [$SPEC#feature-savings-goals-skarbonki]($SPEC#feature-savings-goals-skarbonki)

- [ ] KAL-GOL-001 Create a savings goal
- [ ] KAL-GOL-002 Contribute to a goal
- [ ] KAL-GOL-003 Pace hint against the target date
- [ ] KAL-GOL-004 Close a goal and release the money

$DOD"

create_issue "Reserve funds: emergency cash and 3-month security fund (KAL-FND)" \
  "Backlog" "enhancement,spec:planned,area:funds" \
"Two non-negotiable safety nets tracked against targets: emergency cash at home (2–5k zł) and a security fund covering at least 3 months of real average spending.

**Spec:** [$SPEC#feature-reserve-funds]($SPEC#feature-reserve-funds)

- [ ] KAL-FND-001 Track emergency cash at home
- [ ] KAL-FND-002 Security fund target derives from real spending
- [ ] KAL-FND-003 Warning when a reserve falls below target

$DOD"

create_issue "Debt tracking: who owes what, linked to the ledger (KAL-DBT)" \
  "Backlog" "enhancement,spec:planned,area:insight" \
"Money lent to people gets lost in general transactions. A dedicated panel tracks per-person balances, with entries linked to regular transactions and excluded from expense stats.

**Spec:** [$SPEC#feature-debt-tracking]($SPEC#feature-debt-tracking)

- [ ] KAL-DBT-001 Record money lent to a person
- [ ] KAL-DBT-002 Panel shows balance per person
- [ ] KAL-DBT-003 Repayment reduces the balance
- [ ] KAL-DBT-004 Lent money is not an expense

$DOD"

create_issue "Investment tracking: ETFs, stocks, bonds in net worth (KAL-INV)" \
  "Backlog" "enhancement,spec:planned,area:insight" \
"Beyond cash: holdings with cost basis and valuations, counted into net worth, with contributions linked to transfers.

**Spec:** [$SPEC#feature-investment-tracking]($SPEC#feature-investment-tracking)

- [ ] KAL-INV-001 Add a holding
- [ ] KAL-INV-002 Update the valuation
- [ ] KAL-INV-003 Investments count toward net worth
- [ ] KAL-INV-004 Contribution linked to a transfer

$DOD"

create_issue "AI insights: natural-language monthly summaries and anomalies (KAL-AIN)" \
  "Backlog" "enhancement,spec:planned,area:insight" \
"Plain-language analysis of the ledger — narrative monthly summaries and anomaly call-outs. Commercial layer per the roadmap (paid tier = AI + hosting).

**Spec:** [$SPEC#feature-ai-insights]($SPEC#feature-ai-insights)

- [ ] KAL-AIN-001 Monthly narrative summary
- [ ] KAL-AIN-002 Anomaly is pointed out with context

$DOD"

create_issue "Public API: documented REST coverage of core resources (KAL-API)" \
  "Backlog" "enhancement,spec:planned,area:api" \
"Automation is a first-class exit: everything the UI can do should be scriptable with a bearer token, so users can integrate imports, LLMs, or home automation.

**Spec:** [$SPEC#feature-public-api]($SPEC#feature-public-api)

- [ ] KAL-API-001 Create a transaction via the API
- [ ] KAL-API-002 Read budgets via the API
- [ ] KAL-API-003 API schema is discoverable

$DOD"

echo
echo "==> Done. Review at https://github.com/$REPO/issues"
