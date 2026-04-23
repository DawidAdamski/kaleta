---
plan_id: subscriptions-category-driven
title: Subscriptions — categories as source of truth
area: wizard
effort: medium
status: draft
roadmap_ref: ../product/financial-wizard.md#3-subscriptions
---

# Subscriptions — categories as source of truth

## Intent

The shipped Subscriptions panel uses a detector + explicit `Subscription`
rows. That works but it's disconnected from how users already
categorise their money: power users build a category tree and assign
transactions to it. The natural question "is this a subscription?"
should have the same answer as "is it categorised under
Subscriptions?".

Flip the model: a **"Subscriptions" root category** (with user-defined
children — Monthly / Yearly / Streaming / Software / Memberships / …)
becomes the source of truth. Any transaction whose category sits
under that root is a subscription charge. The panel groups charges by
the child category they belong to. The detector becomes a
"help me categorise recurring charges" assistant rather than the
gatekeeper.

## Scope

### Data model

- A **new Category flag** `is_subscriptions_root: bool` (default false),
  settable on exactly one root category. Identifies the "Subscriptions"
  tree without hard-coding a name.
- OR, simpler: use `CategoryType.SUBSCRIPTION` — but that changes the
  semantics of the existing EXPENSE/INCOME taxonomy. Prefer the flag
  approach (see Open question #1).
- **Seed script** creates the root "Subscriptions" category and three
  starter children (Monthly / Yearly / Other) on fresh DBs. Existing
  DBs get a lightweight migration that creates the root + children if
  none exists yet, marked idempotent.
- `Subscription` model stays as-is (detector candidates still need a
  persistent "I'm tracking this" record). Adding a subscription now
  also sets an optional `category_id` under the Subscriptions tree.

### Detection rewrite

- Detector still runs, but its scope narrows: only surface candidates
  whose transactions are **not already** under the Subscriptions tree.
- New service method `subscription_transactions_grouped(year)` returns
  every transaction under the Subscriptions tree, grouped by
  child-category and merchant.
- Detector confirm flow ("Track") now has **two inputs** in the dialog:
  pick a sub-category (default: Monthly) and optionally overwrite
  name/amount. Confirming **categorises the historical charges**
  (updates every matching tx in the window to the chosen
  sub-category) and creates the `Subscription` row.

### View changes

- Subscriptions panel gains a new top card: **"By category"** — one
  collapsible section per sub-category (Monthly, Yearly, Streaming…)
  showing the merchants + their last-30-days spend + monthly
  contribution. This is the primary view; "Detected recurring
  charges" moves below it.
- "Manage categories" button on the panel links to `/categories`
  with the Subscriptions root pre-selected.

### Out of scope

- Auto-tagging new transactions by merchant (future plan — separate
  rules engine).
- Migrating the existing Subscription list to categories — new
  subscriptions get categorised, legacy ones flagged for review.
- Tag-based grouping (`subscription` tag in seed plan) — the category
  flag is the authoritative mechanism; the tag becomes legacy.

## Acceptance criteria

- Fresh-install seed creates a Subscriptions root category with three
  children (Monthly / Yearly / Other). `is_subscriptions_root` on the
  root is `true`; no other category has it.
- Confirming a detected candidate asks which sub-category to file it
  under, then re-categorises every matching historical transaction
  (same payee or merchant key, same amount bucket, inside the
  detector window) to that sub-category.
- Subscriptions panel shows a "By category" card grouped by child
  category; each group lists merchants and their monthly-equivalent
  totals.
- Detector section only lists candidates that aren't already
  categorised under the Subscriptions tree.
- Widening the detector window and the category membership rule means
  Netflix/Amazon/Disney historical charges can be categorised once
  (even from >24 months ago) and the panel then shows them forever,
  regardless of detector window.

## Touchpoints

- `src/kaleta/models/category.py` — add `is_subscriptions_root` column.
- `alembic/versions/<new>_add_subscriptions_root_flag.py` — migration +
  idempotent seed of root + three children.
- `src/kaleta/services/category_service.py` — helpers:
  `get_subscriptions_root()`, `list_subscription_children()`,
  `ensure_subscriptions_root_and_children()`.
- `src/kaleta/services/subscription_service.py` —
  - `detect_candidates`: filter out transactions already under the
    Subscriptions tree.
  - `subscription_transactions_grouped(year_month)`: new aggregation.
  - `create_from_candidate(cand, *, sub_category_id)`: re-categorise
    matching historical tx + create Subscription.
- `src/kaleta/views/subscriptions.py` — new "By category" card, new
  dialog on Confirm with sub-category picker.
- `src/kaleta/i18n/locales/{en,pl}.json` — keys for the new card,
  dialog, sub-category picker.
- `scripts/seed.py` — create the root + children.
- Tests: category-membership filter, re-categorisation side-effect,
  grouped aggregation.

## Open questions

1. **Flag vs CategoryType vs magic name.** A boolean on Category is
   the lightest; `CategoryType.SUBSCRIPTION` pollutes the
   income/expense dichotomy; hard-coded name is fragile across
   locales. Default: `is_subscriptions_root: bool`.
2. **Multi-level vs flat.** Can a user create
   `Subscriptions > Streaming > Netflix`? v1: flat — direct children
   only. Revisit if users ask.
3. **Re-categorisation scope.** When confirming a candidate, do we
   re-tag only window-matching historical tx or EVERY matching tx
   forever? v1: window only; future tx handled by a tagging-rules
   plan.
4. **What happens when a tracked Subscription's category is deleted?**
   FK already SET NULL on categories; panel shows them under an
   "Uncategorised" pseudo-group.
5. **Interaction with `subscription` tag from the seed plan.** For v1
   we ignore the tag; post-v1 we can fold tag-only matches into the
   same grouping via migration.

## Implementation notes

_(filled as work progresses)_
