# UX audit — feature categorisation in nav and settings

Deliverable of plan [`ux-audit-feature-categorization`](../plans/ux-audit-feature-categorization.md).
Date: 2026-08-09 · Status: proposal for review · Inputs: `views/layout.py`
(NAV_GROUPS), `views/settings/page.py` (tabs), `docs/bdd.md` (workflow map),
registered routes in `src/kaleta/views/`.

## 90-second summary

The sidebar groups pages by *what they are* (Overview / Manage / Tools /
Setup); the BDD spec organises the product by *when the user acts*
(capture → monthly → yearly → insight → setup). Realigning the nav to the
workflow map fixes the "too many options" feeling without deleting any
feature: fewer items visible by default, rarely-used pages collapsed, two
near-duplicate modules merged, and five full pages currently hidden behind
the Wizard hub become first-class citizens of their workflow group.

Key moves (details below):

| # | Move | Cost |
|---|---|---|
| 1 | Regroup sidebar into Capture / Monthly / Plans & funds / Insight / Setup | low |
| 2 | Pin Dashboard + Wizard above the groups; collapse Setup by default | low |
| 3 | Merge Credit Calculator into Credit as a tab (redirect `/credit-calculator`) | low |
| 4 | Move Accounts, Housekeeping, Rules into Setup (rarely touched after day 1) | low |
| 5 | Surface `/wizard/*` pages (Subscriptions, Monthly Readiness, Safety Funds, Personal Loans) in their workflow groups — keep URLs | low |
| 6 | Rename "Budget Plan" → "Annual Plan"; add nav access to `/planned` from Payment Calendar | low |
| 7 | Settings: merge History tab into Data; General absorbs new defaults (per `ux-sidebar-workflow-and-settings` PR 2) | low–med |

Net effect: 20 always-visible nav items → **15 visible + 8 collapsed**,
grouped by the rhythm of use. No URL breaks in phase 1.

## 1. Inventory — current vs proposed

### Sidebar items (NAV_GROUPS today: Overview / Manage / Tools / Setup)

| Page | Route | Current group | Proposed | Rationale (heuristic · BDD ref) |
|---|---|---|---|---|
| Dashboard | `/` | Overview | **Pinned (top)** | Entry point for every session · Workflow 6 Insight |
| Wizard | `/wizard` | Tools | **Pinned (top)** | It is the guided hub, not a "tool"; burying it under Tools contradicts its mentor role · KAL-WIZ |
| Transactions | `/transactions` | Manage | **Capture** | Daily rhythm · Workflow 2, KAL-TXN/KAL-QIK |
| Import | `/import` | Manage | **Capture** | Same session as transaction entry · KAL-CSV |
| Budgets | `/budgets` | Manage | **Monthly** | Monthly close/plan · Workflow 3, KAL-BUD |
| Payment Calendar | `/payment-calendar` | Manage | **Monthly** | Monthly planning view, mislabelled "Manage" today · KAL-PLN |
| Monthly Readiness | `/wizard/monthly-readiness` | *(hidden in Wizard)* | **Monthly** | Recognition rather than recall — a monthly ritual page invisible in the nav · KAL-RDY |
| Subscriptions | `/wizard/subscriptions` | *(hidden in Wizard)* | **Monthly** | Recurring-cost review is monthly · KAL-SUB |
| Budget Plan → **Annual Plan** | `/budget-plan` | Manage | **Plans & funds** | It is the *annual* grid; sitting next to "Budgets" the two names collide (match system ↔ real world) · KAL-BUD-Annual |
| Safety Funds | `/wizard/safety-funds` | *(hidden in Wizard)* | **Plans & funds** | Ongoing goals, not a wizard step · Workflow 5, KAL-FND/KAL-GOL |
| Personal Loans | `/wizard/personal-loans` | *(hidden in Wizard)* | **Plans & funds** | First-class debt tracking · KAL-DBT |
| Reports | `/reports` | Overview | **Insight** | Workflow 6 · KAL-RPT |
| Net Worth | `/net-worth` | Overview | **Insight** | Workflow 6 · KAL-INV |
| Forecast | `/forecast` | Tools | **Insight** | Analysis, not a tool you configure · KAL-FCT |
| Credit | `/credit` | Tools | **Insight** | Cards/loans overview · KAL-CRD |
| Credit Calculator | `/credit-calculator` | Tools | **→ tab inside Credit** | Two adjacent nav items for one domain; calculator is stateless (ADR-023) — classic consolidation win |
| Accounts | `/accounts` | Overview | **Setup (collapsed)** | CRUD'd rarely after day 1; balances live on Dashboard/Net Worth · Workflow 1, KAL-ACC |
| Institutions | `/institutions` | Setup | Setup | unchanged · KAL-INS |
| Categories | `/categories` | Setup | Setup | unchanged · KAL-CAT |
| Tags | `/tags` | Setup | Setup | unchanged · KAL-TAG |
| Payees | `/payees` | Setup | Setup | unchanged · KAL-PAY |
| Rules | `/rules` | Setup | Setup | set-and-forget config · KAL-RUL |
| Housekeeping | `/housekeeping` | Tools | **Setup (collapsed)** | Maintenance, visited on demand · KAL-HSK |
| Settings | `/settings` | Setup | Setup (last item) | unchanged |
| Planned transactions | `/planned` | *(no nav entry)* | link from Payment Calendar toolbar | Definitions page for what the calendar shows; keep out of nav, but make reachable in one click · KAL-PLN |
| Budget Builder | `/wizard/budget-builder` | *(hidden in Wizard)* | stays wizard-only | True guided flow, correct as a hub step · KAL-WIZ |
| API docs | `/api-docs` | below groups | unchanged | |

### Proposed sidebar tree

```
◆ Dashboard
◆ Wizard (Przewodnik)
── Capture ─────────────  (daily / weekly)
   Transactions
   Import
── Monthly cycle ───────
   Budgets
   Payment Calendar
   Monthly Readiness
   Subscriptions
── Plans & funds ───────  (yearly / ongoing)
   Annual Plan
   Safety Funds
   Personal Loans
── Insight ─────────────
   Reports
   Net Worth
   Forecast
   Credit (incl. Calculator tab)
── Setup ── [collapsed by default]
   Accounts · Institutions · Categories · Tags · Payees · Rules ·
   Housekeeping · Settings
```

15 items visible by default (2 pinned + 13 grouped) vs 20 today; the 8
Setup items appear on one click and the collapsed state persists per user
(mechanism already exists in `layout.py`).

## 2. Settings tabs — current vs proposed

Current: General · Appearance · Features · Data · Security · History · About (7).

| Tab | Proposal | Rationale |
|---|---|---|
| General | keep; absorb defaults from `ux-sidebar-workflow-and-settings` PR 2 (currency, formats, week start, default account) | one obvious home for "how the app behaves" |
| Appearance | keep | distinct mental model (theme/density) |
| Features | keep; add detection thresholds (transfer window, subscription sensitivity) per PR 2 | consolidates hidden hardcodes |
| Data | keep; **absorb History (audit log)** | audit log is a data concern; 7 tabs → 6 reduces scanning (recognition) |
| Security | keep | auth/tokens deserve isolation |
| About | keep | |

Cost: low (tab shuffle + i18n); History merge is medium only if the audit
log grows its own filters later.

## 3. Nielsen heuristics — findings behind the moves

- **Match between system and real world:** "Manage" and "Tools" are
  developer categories; users think in rhythms (daily entry, monthly close,
  yearly plan). The BDD workflow map *is* the users' mental model — the nav
  should mirror it. (Moves 1, 5, 6.)
- **Recognition rather than recall:** four full modules (Subscriptions,
  Monthly Readiness, Safety Funds, Personal Loans) are invisible unless the
  user remembers they live inside the Wizard. (Move 5.)
- **Consistency and standards:** "Budgets" vs "Budget Plan" reads as a
  duplicate; renaming to "Annual Plan" disambiguates cadence. (Move 6.)
- **Aesthetic and minimalist design:** 20 flat items in 4 always-open
  groups exceeds comfortable scanning (~7±2 per view); pinning the two
  entry points and collapsing Setup brings the default view to ~15 with
  clear section rhythm. (Moves 2, 4.)
- **Flexibility and efficiency of use:** merging Credit Calculator into
  Credit removes a decision point without removing the feature. (Move 3.)

## 4. Migration list — cost-ranked

**Phase A — no URL changes (one PR, `views/layout.py` + i18n only):**
1. New NAV_GROUPS per the tree above; Setup collapsed by default.
2. Pin Dashboard + Wizard above groups.
3. Nav entries for the four `/wizard/*` pages (URLs unchanged).
4. Rename i18n key `nav.budget_plan` → "Annual Plan" / "Plan roczny".
5. e2e smoke: every nav item routes (guards the regroup — test exists per
   plan `ux-sidebar-workflow-and-settings`).

**Phase B — small redirects (separate PR):**
6. `/credit-calculator` → tab inside `/credit`, keep a redirect.
7. Payment Calendar toolbar link to `/planned`.
8. Settings: History → Data merge; General/Features additions.

**Phase C — optional, higher cost (only if Phase A/B prove insufficient):**
9. URL renames (`/wizard/subscriptions` → `/subscriptions` etc.) —
   requires redirects, BDD retagging, e2e updates. **Recommendation: skip
   for now**; URLs are invisible in a PWA sidebar app.

## 5. Out of scope

Dashboard widget redesign (`q4-dashboard-design-refresh`), wizard internal
panel ordering (audit it after Phase A lands — the hub's role shrinks once
its sub-pages are in the nav), multi-user settings (2027).
