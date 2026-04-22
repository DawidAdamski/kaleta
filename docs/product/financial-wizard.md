# Financial Wizard — Assistant Model

> Status: product concept. Some scaffolding in `views/wizard.py`;
> sections below are coming-soon placeholders.
> Parent: [roadmap](../roadmap.md).

## Intent

The Wizard is not a one-time setup flow — it is an **always-available
assistant** that helps the user execute recurring financial tasks and
*reminds* them when something is overdue. Every section is a guided,
interactive walkthrough rather than a static report. The wizard is the
counterpart to the dashboard:

- **Dashboard** = state (what is).
- **Wizard** = action (what to do next).

AI-powered extensions (narrative analysis, anomaly explanations,
auto-suggestions) are reserved for a paid tier. The base wizard works
without any AI.

## Sections

### 1. Getting Started

Already live as the collapsible onboarding card.

- **Purpose redefined:** not only "create your first account", but
  also a *mentor* that recommends which dashboard / view is the right
  tool for the task the user is currently trying to do. Think of it
  as contextual product tour — always accessible, never intrusive.
- **Future content:**
  - "You just imported transactions — open the Transactions view to
    categorise bulk."
  - "You have budgets defined — pin Budget Progress widget to the
    dashboard."
  - "Net worth has grown 5% this month — see the Net Worth view for
    the breakdown."

### 2. Monthly Readiness

Two jobs in one:

- **Plan the next month.** A guided flow that helps the user fill
  in planned transactions for the upcoming month — recurring bills,
  expected salary, irregular payments flagged from past months.
  YNAB-style: every złoty is assigned. The flow surfaces any amount
  not yet allocated.
- **Audit the current / past month.** Deep dive on the month just
  closed:
  - periodic deviations (category X usually costs 400, this month
    600 — flag as "significant");
  - periodic repeats (anything that reliably appears every
    3/6/12 months);
  - large one-off items that could be standardised as planned
    transactions.

**Reminders.** The section should push reminders via the user's
preferred channel — email, messenger, or in-app. Free tier: basic
"don't forget to plan next month" nudge. Paid tier: AI-generated
monthly narrative with insights.

**Dependencies:** planned transactions module, notifications (new),
AI service integration (paid tier).

### 3. Subscriptions

Tracks recurring paid services — from obvious ones (streaming,
software) to modern hidden subscriptions (heated seats in a car,
enhanced app features).

- **Detection:** transactions tagged with category *or* tag
  `subscription` are considered subscriptions. The wizard doesn't
  auto-classify; it asks the user whether a recurring payment looks
  like a subscription and offers to tag it.
- **Periodic review:** from time to time (every N months,
  configurable), the wizard walks through the active list and asks
  "do you still use this?" / "do you still need this?".
- **Categorisation:** subscriptions can be grouped by user-defined
  subcategory (streaming, SaaS, memberships, vehicle extras, …).
- **Annual drain view:** per subscription, per group, overall —
  monthly × 12 so the user sees the real yearly cost.
- **Management links:** each subscription entry can hold a
  subscribe / unsubscribe URL so cancellation is one click away.
- **Future:** predictive price-change alerts (paid tier?).

**Dependencies:** tags / categories, subscription grouping
(new taxonomy under categories or separate `SubscriptionGroup`
table), URL field on a per-payee or per-subscription record.

### 4. Safety & Reserve Funds

Four related goals, configurable per user:

- **Emergency fund (3–6 months of essentials).** Wizard calculates
  essential monthly outgoings from history, shows a target range,
  tracks progress against a dedicated savings account.
- **Irregular expenses fund.** Quarterly / semi-annual / annual
  recurring expenses (insurance, car inspection, property tax,
  appliances). The wizard:
  1. Lets the user pick which recurring expenses count as
     "irregular" from a list drawn from planned / historical
     transactions.
  2. Sums them.
  3. Divides by **10 or 12** (user chooses — a 10-month denominator
     builds a buffer faster and tolerates December overruns).
  4. Proposes that amount as a monthly transfer to the irregular
     fund.
- **Vacation fund.** The same pattern, targeted at holiday planning:
  declare next trip's budget + date, wizard proposes monthly
  set-aside.
- **Entrepreneur's holiday / time-off fund.** Extra for self-employed
  users: replicates the salary buffer idea, for months when no work
  is billed (vacation, sick leave, slow season).

**Dependencies:** savings account concept (or fund as first-class
entity), transfers, planned transactions.

### 5. Budget Builder

Annual budget construction, complementing Monthly Readiness.

- **Cadence:** once a year (+ ad-hoc revisions). Not for month-to-
  month tweaks — that's Monthly Readiness.
- **Inputs:** last 3–6–12 months of actuals, income projection,
  committed recurring costs, fund contributions (emergency /
  irregular / vacation).
- **Output:** a full-year plan that becomes the default source for
  monthly budgets.
- **Relationship with Monthly Readiness:** Budget Builder creates;
  Monthly Readiness verifies & adjusts.

### 6. Personal Loans Register

Track money lent to / borrowed from people (not banks).

- **Entity:** `PersonalLoan` — counterparty, direction (lent /
  borrowed), amount, date, expected return date, optional interest,
  status (open / partially settled / settled).
- **Linking:** when the loan is issued or repaid, it links to the
  transactions that move the money.
- **Reminders:** the wizard nudges the user as return dates approach.

## Shared wizard patterns

- **Every section supports reminders** via the same notification
  channel — email / messenger / in-app. Channel configured once
  per user in Settings.
- **Every section produces action items** (suggested planned
  transactions, proposed transfers, review prompts). Action items
  show up on the dashboard (if the user pins the Wizard widget) and
  in the relevant section.
- **AI-powered deep analysis** is the same toggle in every section:
  off for free users, on for paid. When off, the section falls back
  to heuristics.

## Open questions

- **Fund representation:** is a "fund" a savings account, a virtual
  bucket on top of an account, or a new first-class entity
  (`Fund` table)? Leaning first-class — it lets us track
  target vs current without conflating with account balance.
- **Notification infrastructure:** per-user channel config lives
  in Settings; which dispatch mechanism for email / messenger?
  (initial idea: email via SMTP; messenger via webhook URL).
- **Subscription taxonomy:** do we use the existing category tree
  with a parent "Subscriptions", or a separate `SubscriptionGroup`
  entity? The former is simpler; the latter lets a subscription
  keep its operational category (e.g. *Entertainment*) while being
  grouped under *Streaming* for drain reporting.
- **Paid tier boundary:** list exactly which features sit behind
  the paywall. Draft:
  - AI monthly narrative,
  - AI anomaly explanations,
  - AI-assisted subscription classification,
  - AI-driven budget proposals.
  Everything else stays free.
- **Personal loans vs transactions:** when a loan is repaid in
  instalments, do we generate a planned-transaction schedule the
  way we plan to for Credit? Probably yes — consistency.
