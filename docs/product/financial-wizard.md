# Financial Wizard — Assistant Model

> Status: product concept. Some scaffolding in `views/wizard.py`;
> sections below that have no page yet are labelled "Planned" on it.
> Parent: [roadmap](../roadmap.md).

**The `/wizard` page** reads top to bottom as: hero, then one mentor
suggestion in an accent-ruled card, then Setup as four compact
done-cards (collapsed once all four are ticked), then a single
two-column index of every routine below — the ones with a page behind
them first, each with an `Open` link; the rest muted and marked
"Planned". The sections below are eyebrow labels inside that index, not
six coloured cards.

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

Already live as the collapsible Setup card — four done-cards, collapsed
by default once all four are ticked.

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

### 3. Unplanned Expenses Radar {#3-unplanned-expenses-radar}

The Monthly Readiness flow above can only plan what the user
remembers. The radar (`/wizard/unplanned-radar`) covers what they
forget: the irregular costs that arrive months or years apart — car
service, dentist, school fees, chimney sweep, insurance top-ups.

- **Detection:** history is grouped by payee, or by a
  description-derived merchant key for rows that never got a payee.
  A group counts as a pattern when consecutive charges sit 60–450
  days apart and every amount lands within ±30 % of the median. Two
  occurrences are enough — irregular costs rarely give you three.
  Anything already covered by an active planned transaction, an
  active subscription, the Subscriptions category tree, or an earlier
  dismissal is filtered out.
- **Amount drift is expected, not suspicious.** A subscription that
  moves 5 % is news; a car service that moves 15 % is Tuesday. The
  radar reports the median amount and the dates it saw it on, so the
  rhythm is visible without the row turning into a ledger.
- **Two actions per row.** *Plan it* opens a pre-filled planned
  transaction (name, median amount, inferred rhythm, the account and
  category the charges used, first occurrence at the estimated next
  date). *Not a repeating cost* is persisted, so the row does not
  come back on the next page load.
- **Evidence stays attached.** Converting links the source charges to
  the new plan, so the plan carries the payments that justified it
  rather than an untraceable number.
- **Feeds the irregular fund.** The page totals the yearly estimates
  and offers the monthly equivalent as the amount to set aside, with
  a link to [Safety & Reserve Funds](#4-safety--reserve-funds) — the
  radar is the natural source for that fund's item list.
- **Boundary with Subscriptions:** the monthly rhythm belongs to the
  subscription tracker. If the radar starts listing streaming
  services, its minimum gap is wrong.

**Dependencies:** planned transactions module, payee / merchant-key
normalisation shared with the subscription detector, the dismissal
table (shared, keyed by kind).

### 4. Subscriptions {#3-subscriptions}

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

### 5. Safety & Reserve Funds {#4-safety--reserve-funds}

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

### 6. Budget Builder {#5-budget-builder}

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

### 7. Personal Loans Register {#6-personal-loans}

Track money lent to / borrowed from people (not banks).

- **Entity:** `PersonalLoan` — counterparty, direction (lent /
  borrowed), amount, date, expected return date, optional interest,
  status (open / partially settled / settled).
- **Linking:** when the loan is issued or repaid, it links to the
  transactions that move the money.
- **Reminders:** the wizard nudges the user as return dates approach.

### 7. Pay Yourself a Salary {#7-pay-yourself-a-salary}

For the entrepreneur persona: irregular inflows (invoices,
commission, royalties) smoothed into one fixed monthly transfer, so
the household budget stops swinging with the invoicing calendar.

- **Cadence:** revisit quarterly, or whenever the income mix
  changes. Not a monthly chore.
- **Inputs:** non-transfer `INCOME` transactions over a window of
  recent **complete** months (6 / 12 / 24, default 12). The running
  month is always partial and never counts. The series starts at the
  first month inside the window that earned anything — leading empty
  months are missing data, not zero-income months — while gaps and
  trailing months after it count as zero, because a dry month is
  real information about how much the income can drop.
- **Proposal:** the worst month of that window by default, matching
  the promise of the tile. The lower quartile and the median are
  offered as less conservative alternatives, and the amount is
  editable — an override replays the buffer against whatever the
  user actually picks.
- **Buffer:** the window replayed month by month. Everything a month
  earns above the salary accumulates; a lean month draws it down. The
  chart shows income bars, the salary line, and the running buffer.
- **Output:** one action item — a monthly `TRANSFER` planned
  transaction from the inflow account to the personal account, which
  the Payment Calendar and the forecast then pick up like any other
  recurring item. The panel schedules nothing itself.
- **Limits (v1):** single-currency income. Income in more than one
  currency is summed as-is with a warning; no conversion. Tax and ZUS
  modelling are out — the salary is gross of both.
- **Degradation:** fewer than 3 complete months of income and the
  panel shows a hint instead of a proposal.

### 8. What-if Scenarios {#8-what-if-scenarios}

The panel (`/wizard/scenarios`) answers "can I afford this?" without a
spreadsheet. It is **not** a second forecasting engine: the baseline is
exactly what the [Forecast](../architecture.md) page draws for the same
account and horizon, and everything the panel does is laid on top of it.

- **Three changes, and only three.** An *income change* (±% or a fixed
  amount from a date onward), a *one-off amount* (a purchase or a
  windfall on one day), and a *recurring amount* (a new bill or a new
  income stream, monthly / quarterly / yearly). Amounts are signed the
  way the ledger is: negative takes money out.
- **Compiled to dated events, not to a slope.** "A new 300 zł
  subscription from March" becomes thirty-odd separate withdrawals on
  the days they happen, so the projected line steps where the money
  actually leaves rather than sagging smoothly through it.
- **A percentage is read against real income.** The balance series
  records what is left over, never what came in, so "−30%" has no
  meaning on its own. It is read against the selected account's own
  income over the same trailing window the runway uses — the household
  total would apply a cut the account never took.
- **The verdict, in three figures.** Monthly cashflow; balance at the
  horizon before → after; and emergency-fund runway before → after,
  plus one sentence about whether — and when — the balance runs out.
- **One runway, not two — and it only ever gets worse.** The runway is
  the Safety & Reserve Funds definition (`balance ÷ monthly essential
  spend`), borrowed rather than reimplemented. Because the figure asks
  "if income stopped, how long would this last", **nothing a scenario
  adds to income can lengthen it** — not a raise, not a new recurring
  income stream, not a windfall. Income has already stopped inside the
  question; those all move the projected balance instead, which is
  where a reader sees them. What shortens it is spending: a purchase
  draws the fund down, because nothing records which pot it comes out
  of, and a new bill raises the burn the fund is divided by.
- **Horizon:** 12 months by default, 24 at most — the forecast's own
  scale, not a third one.
- **No Prophet required.** The panel runs on whichever forecaster is
  installed; the optional extra changes the baseline's quality, never
  the panel's availability.
- **Nothing is saved (v1).** The change list lives as long as the page.
  Named, persisted scenarios are a follow-up once the shape proves out.
- **Boundary with Budget Builder:** the simulator only asks. Applying a
  scenario to the plan — "make this my budget" — is a separate future
  plan, not a button here.

**Dependencies:** `forecast_service` (baseline, read-only),
`reserve_fund_service` (runway maths, read-only), the shared forecast
chart component.

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
