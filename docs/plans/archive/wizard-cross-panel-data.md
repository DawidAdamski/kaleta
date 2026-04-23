---
plan_id: wizard-cross-panel-data
title: Wizard — cross-panel data flow
area: wizard
effort: large
status: archived
archived_at: 2026-04-23
roadmap_ref: ../product/financial-wizard.md
---

# Wizard — cross-panel data flow

## Intent

Each wizard panel was built as a self-contained unit: Budget Builder
asks the user to retype everything, Subscriptions lives alone,
Safety Funds stores its monthly contribution targets but no other
view reads them, Monthly Readiness already pulls a few things but
misses others. The result is that a power user with 10 subscriptions,
3 reserve funds, 8 recurring planned transactions, and a dozen
categories has to re-enter the same numbers in several places —
exactly the friction the wizard was meant to remove.

Wire the panels together so each one consumes the authoritative data
that already exists elsewhere, with clear source-of-truth rules and
no bidirectional sync ambiguity.

## Scope

### Direction of flow (v1, read-only projections)

Source of truth → where it surfaces:

| Source                      | Consumers                                                  |
|-----------------------------|------------------------------------------------------------|
| Subscriptions (once built)  | Budget Builder (Fixed), Monthly Readiness Stage 4, Payment Calendar |
| Planned Transactions        | Budget Builder (Income + Fixed/Variable), Monthly Readiness Stages 2/4 (already partial) |
| Safety/Reserve Funds        | Budget Builder (new Reserves row), Monthly Readiness Stage 3 |
| Personal Loans (once built) | Budget Builder (Fixed), Payment Calendar                   |
| Budgets (per-category)      | already used by Dashboard; unchanged                       |

### Budget Builder changes

- Each section (Income, Fixed, Variable) gains a **"From other panels"**
  read-only sub-header that lists pulled items as disabled rows with
  a source badge (🔒 Subscription / 🔒 Planned / 🔒 Reserve).
- Pulled rows sum into the section total alongside user-typed rows.
- Each pulled row has a cross-link ("Edit in Subscriptions →") that
  navigates to the source panel; Budget Builder itself never edits
  the source record.
- Add a new **Reserves** section (4th card) that pulls each active
  ReserveFund's declared monthly contribution (see Open Question #2
  on where that number comes from).

### Monthly Readiness changes

- Stage 3 (Allocate): preview now includes a "Reserves" row per
  active fund so allocation isn't silently skipping them.
- Stage 4 (Acknowledge bills): merges Subscription next-charge dates
  into the planned-bills list (deduping against
  `PlannedTransaction`s that already cover the same charge).

### Payment Calendar changes

- Day bubbles include subscription charges alongside planned
  transactions. Visual distinction: same colour, small subscription
  icon instead of generic "planned" icon.

### Not in scope (v1)

- **Bidirectional edit** — editing a subscription's amount from
  Budget Builder. Source panel remains the only editor.
- **Auto-categorisation of pulled rows** into user's Category tree.
- **AI suggestions** ("you have 5 subscriptions with no budget
  coverage — create a subscriptions category?").
- **Breakage-detection** when a pulled source is deleted after the
  builder saved. Yearly plan snapshots stay as-written.

## Acceptance criteria

- Given 3 active subscriptions totalling 250 PLN/month, the Budget
  Builder Fixed section shows 3 pulled rows + sub-total 250 PLN in
  the Fixed column's total line, additive to any user-typed rows.
- Clicking a pulled subscription's cross-link navigates to
  `/wizard/subscriptions` (or wherever the panel lands).
- Deleting a subscription and refreshing Budget Builder removes the
  row; already-saved yearly plans are unaffected (user-typed rows
  copied from that subscription, if any, persist as ordinary rows).
- Monthly Readiness Stage 3's "Copy budgets forward" preview lists a
  "Reserves" group with a row per active reserve fund showing its
  monthly contribution.
- Payment Calendar's day bubble for a day with both a planned
  transaction and a subscription charge shows both entries distinct
  from one another.
- No pulled data mutates when viewed — view-only rows are visibly
  disabled (greyed, no edit affordance).

## Touchpoints

### New

- `src/kaleta/services/wizard_projection_service.py` — central
  aggregator. Methods like
  `get_budget_builder_sources(year)`,
  `get_monthly_readiness_sources(year, month)`,
  `get_payment_calendar_sources(date_range)`.
  Returns Pydantic projection structs (below) assembled from existing
  services.

### New schemas

- `src/kaleta/schemas/wizard_projections.py`:
  - `PulledRow` (source_kind: Literal["subscription", "planned",
    "reserve", "loan"], source_id: int, label: str, amount: Decimal,
    cadence: Literal["monthly", "annual", ...]).
  - `BudgetBuilderProjection` (income: list[PulledRow],
    fixed: list[PulledRow], variable: list[PulledRow],
    reserves: list[PulledRow]).
  - Similar for `MonthlyReadinessProjection`,
    `PaymentCalendarProjection`.

### Changed views

- `src/kaleta/views/budget_builder.py` — render pulled rows,
  add Reserves section, wire cross-links.
- `src/kaleta/views/monthly_readiness.py` — extend Stage 3 preview
  and Stage 4 acknowledgement list.
- `src/kaleta/views/payment_calendar.py` — merge subscription
  charges into day bubbles.

### Changed i18n

- `src/kaleta/i18n/locales/{en,pl}.json` — new keys for the
  "From other panels" sub-header, source badges, cross-link labels,
  and the Reserves section heading.

### Tests

- `tests/unit/services/test_wizard_projection_service.py` —
  unit-test each projection method independently of the views.
- Extend existing Monthly Readiness tests for the new Stage 3 /
  Stage 4 pulled rows.

## Open questions

1. **Source-panel readiness.** Subscriptions and Personal Loans are
   still draft plans. Land this plan *after* Subscriptions ships (so
   there's real source data), but design the projection service now
   so each source becomes a trivial add when its panel ships.
2. **Where does a reserve fund's monthly contribution live?** Today
   the model has `target_amount` + `emergency_multiplier` but no
   explicit monthly contribution. Options:
   - Add `monthly_contribution: Decimal | None` to `ReserveFund`.
   - Derive it on the fly: `(target - balance) / months_remaining`
     where `months_remaining` comes from a new timeline field.
   - Leave it user-entered in the Reserves section of Budget Builder
     (breaks the "single source of truth" principle).
   Decision needed before building the Budget Builder Reserves
   section.
3. **Pulled-row display when a yearly plan was saved before a source
   existed.** If the user saves Fixed = [Netflix 50 PLN typed as a
   free line], then later creates a Subscription "Netflix 50 PLN",
   do we deduplicate? v1 answer: **no**, leave both visible; the
   user can delete the typed line manually. Revisit if friction is
   real.
4. **Cadence handling.** Subscriptions can be annual/quarterly; the
   Budget Builder columns are monthly-equivalent. Normalise to
   monthly in the projection (`annual_amount / 12`) with the raw
   cadence still exposed for tooltips.
5. **Performance.** Each wizard panel would now hit several services
   on load. In practice these are tiny tables, but if latency shows
   up, add a short in-process cache keyed by `(user_id, year)`.

## Implementation notes
_Filled in as work progresses._

## Implementation

Landed on 2026-04-23.

| SHA | Author | Date | Message |
|---|---|---|---|
| `827be94` | Dawid | 2026-04-23 | feat(wizard): cross-panel projection layer |

**Files changed:**
- `src/kaleta/services/wizard_projection_service.py` (new)
- `src/kaleta/services/__init__.py`
- `src/kaleta/schemas/wizard_projections.py` (new — PulledRow, BudgetBuilderProjection, PaymentCalendarProjection, SubscriptionCharge)
- `src/kaleta/views/budget_builder.py`
- `src/kaleta/views/payment_calendar.py`
- `src/kaleta/i18n/locales/en.json`
- `src/kaleta/i18n/locales/pl.json`
- `tests/unit/services/test_wizard_projection_service.py` (19 tests)
- `docs/architecture.md`
- `docs/tech-stack.md`
- `README.md`

**What shipped:**
- **WizardProjectionService** with two methods: `get_budget_builder_sources(year)` returning a `BudgetBuilderProjection` and `get_payment_calendar_sources(start, end)` returning a `PaymentCalendarProjection`. Pure aggregation over existing services — zero mutation.
- **PulledRow** schema carries `source_kind` ("subscription" | "planned" | "reserve" | "loan"), `source_id`, `label`, monthly `amount`, a human-readable `cadence` tag, and an optional `href` for the cross-link.
- **Budget Builder** now pulls: Income from active planned transactions with type INCOME; Fixed from active subscriptions, loans (LoanProfile.monthly_payment), and active planned expenses (non-transfer, not ONCE) sorted subscription → loan → planned; Reserves from non-archived reserve funds, monthly contribution derived as `target ÷ multiplier` for emergency funds (honours the safety-funds-months-bar chunk rule) or `target ÷ 12` otherwise. Each pulled row renders with a lock icon, source badge, cadence tooltip, a monthly / yearly amount pair, and a cross-link button. A "From other panels: X" subtotal sits above the yearly grand total.
- **Payment Calendar** projects subscription charges onto the viewed month: day bubbles combine planned and subscription counts/outflows; the drawer shows a "Subscription charges" section under the normal "Items for this day" block.
- **Monthly-equivalent conversion helpers** (`_monthly_from_subscription`, `_monthly_from_planned`, `_monthly_from_reserve`) live at module level so tests cover them pure.
- **19 unit tests** — Netflix monthly vs Amazon Prime yearly conversion, YEARLY planned ÷ 12, BIWEEKLY with interval 2, ONCE → zero (skipped), emergency multiplier vs vacation target/12, service returns empty on empty DB, ordering is deterministic subscription-first, cancelled subscriptions excluded, archived reserves excluded, payment calendar window walking.
- **Browser-verified**: Budget Builder renders Fixed rows from real planned transactions with correct monthly/yearly totals; Reserve funds show derived monthly contributions.

**Partial coverage / deferred:**
- **Monthly Readiness integration** — Stage 3 Reserves group and Stage 4 Subscription-merge were in scope but not shipped. The service surface supports them; the Readiness view would need a `_render_pulled_rows` pass. Flagged as next small follow-up.
- **Variable section pulled rows** — planned ONCE expenses are explicitly skipped (no recurring rate), so Variable's pulled list is empty in v1. Add an alternative projection field if one-off budget reminders are wanted.
- **Deduplication** (Open Question #3) — not implemented; if a user typed "Netflix 50 PLN" in Fixed and later created a Subscription for it, both rows are visible. Plan's v1 decision was explicit: leave both visible.
- **Breakage detection** — already-saved YearlyPlans are not recomputed when a source disappears (plan's out-of-scope).
- **Per-call caching** — each page load hits 4 services; fine in practice on tiny tables. Add a short cache if latency shows up.
- **Personal-loan cross-link target** — routes to `/credit` rather than a deep-link to the specific loan row (Credit view has no per-row permalinks yet).
- **Subscription-charge rendering in the calendar** uses the monthly cadence projected forward from `first_seen_at`; irregular timing captured in Transactions is not reflected.

## Sequencing recommendation

1. Ship `wizard-subscriptions` first (prerequisite source of truth).
2. Pick question #2 (reserve monthly contribution) — small model
   migration if we add a field.
3. Land the projection service + schemas as the foundation.
4. Wire Budget Builder consumers.
5. Wire Monthly Readiness consumers.
6. Wire Payment Calendar consumers.
7. When `wizard-personal-loans` ships, add a single source in the
   projection service — no panel-side work.
