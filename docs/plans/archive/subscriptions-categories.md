---
plan_id: subscriptions-categories
title: Subscriptions by what they are — streaming, software, phone — not by how often they bill
area: subscriptions
effort: medium
status: archived
archived_at: 2026-10-12
roadmap_ref: ../../roadmap.md#subscriptions
---

# Subscriptions by what they are — streaming, software, phone — not by how often they bill

## Intent

The user wants to see their subscriptions grouped by *what they pay for* — streaming,
music, software, phone and internet, press, fitness, cloud storage — with a total per
group, and to file each subscription under one of them. Today the Subscriptions tree
(ADR-28) has three children, Monthly / Yearly / Other: a split by billing period, which
`Subscription.cadence_days` already records, so the tree says nothing the row does not.

## What exists (2026-10-12)

- ADR-28: one category carries `is_subscriptions_root`; its direct children are the
  definition of "a subscription charge". `create_from_candidate(..., sub_category_id=…)`
  re-files the matching history under the chosen child.
- `Subscription.category_id` (an expense category) and the add/edit dialog's select
  (`views/subscriptions/dialogs.py`); the panel's "By category" card groups the last 90
  days of charges by child category and merchant.
- The children are seeded as Miesięczne / Roczne / Inne (`seeders/catalog.py`,
  migration `a4e9b2f1c6d8`).

## Scope

- **Purpose children instead of cadence children**: the seeded tree becomes Streaming
  wideo, Muzyka i audio, Oprogramowanie i aplikacje, Telefon i internet, Prasa i
  czytanie, Sport i zdrowie, Chmura i kopie, Inne (English names in the English seed).
  A migration moves an existing family's untouched cadence children (no user edits, by
  name) to "Inne"/"Other" and adds the purpose children; a tree the user has edited is
  left alone apart from adding the missing purpose children.
- **The subscriptions list grouped by category**: one section per child with its monthly
  and yearly total (the existing totals, per group), the category on each row, and a
  filter.
- **Filing a subscription**: the category select in the dialog lists the purpose
  children; changing it re-files the subscription's matching history the way tracking a
  candidate does (ADR-28's consequence), after a confirmation that says how many charges
  move.
- **A suggestion from the merchant**: a curated map of well-known merchants (Netflix,
  Spotify, YouTube, Microsoft, Google One, Orange, Play, …) proposes the child when a
  candidate is tracked; the user can change it.
- BDD: new `KAL-SUB-*` scenarios for the grouping, re-filing and the suggestion.

## Not in scope

- Multi-level subscription trees (ADR-28 keeps one level).
- Budgets per subscription group (they are ordinary categories, so the budget grid
  already covers them).

## Acceptance criteria

- `uv run pytest tests/integration/test_subscription_categories.py -q`
- `uv run pytest tests/e2e/test_subscriptions.py -q`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

## Touchpoints

`src/kaleta/seeders/catalog.py`, `alembic/versions/<new>_subscription_purpose_children.py`,
`src/kaleta/services/subscription_service.py`, `src/kaleta/services/category_service.py`,
`src/kaleta/views/subscriptions/{page,dialogs,helpers}.py`, `src/kaleta/i18n/locales/*.json`,
`docs/adr/028-…` (amend: children by purpose), `docs/bdd.md`.

## Open questions

- Keep the cadence children for families that use them? Default: no new ones; existing
  ones that hold charges stay as they are (they are the user's data), untouched empty
  ones go.
- Should a subscription's own `category_id` (an expense category outside the tree) stay?
  Default: yes — it is what the charge is budgeted under; the purpose child is where it
  is filed. Decide during implementation after reading how the two are used today.

## Implementation notes

### Delivery in two PRs

- **Part A — the tree**: the purpose children replace the cadence ones (added at runtime,
  removing an *empty, unreferenced, default-named* cadence child — **not** a migration, see
  below), the example seed, and the "By category" grouping (which already reads the tree).
  Tests that named the cadence children move to the purpose ones.
- **Part B — filing**: the add/edit dialog files a subscription under a purpose child and
  re-files its matching history (generalising `_recategorise_matching` from a candidate to a
  subscription), and a curated merchant→child map suggests the child when a candidate is
  tracked.

### Decisions (Part A)

- **The purpose children** (PL / EN): Streaming wideo / Streaming, Muzyka i audio / Music &
  audio, Oprogramowanie i aplikacje / Software & apps, Telefon i internet / Phone &
  internet, Prasa i czytanie / News & reading, Sport i zdrowie / Fitness & health, Chmura i
  kopie / Cloud & backup, Inne / Other.
- **One concept, one column** (open question 2): a subscription's purpose is its
  `category_id` — the model has one, the "By category" card already reads membership from the
  *transactions'* category, and filing (Part B) sets both. No second column, no migration for
  one.
- **Removing cadence children, but only when safe** (open question 1): `ensure_...` deletes
  a cadence child **only** when its name is one of the shipped *billing-period* defaults
  (`Monthly`/`Yearly`, `Miesięczne`/`Roczne`), it is a leaf (no sub-categories), and nothing
  references it — no transaction, split, budget, planned transaction, subscription,
  categorisation rule, reserve-fund or irregular-item category. The catch-all `Other`/`Inne`
  is deliberately *not* on this list: it is the catch-all in both the old cadence tree and
  the new purpose tree, so an old `Other` simply becomes the purpose `Other` and is never
  removed. A fresh family's billing-period children are empty, so a new install ends with the
  eight purpose children alone; a family that filed charges under one keeps it beside the new
  ones, and a renamed child is the user's and is never touched. Deleting a category with
  inbound rows across the schema is never done.
- **Idempotent by blind index**: children are added and matched by `exact_index(name)` (the
  taxonomy seeder's pattern), not a raw string compare, so re-running adds nothing and the
  match is encryption- and case-stable. `ensure_subscriptions_root_and_children` is taught
  the same blind-index compare and the purpose default names.

- **Runtime, not a migration** (decided during implementation): category names are
  `EncryptedText`, so a migration cannot *create* a child without the family's data key
  (and `alembic upgrade head` on a locked tenant raises `TenantLockedError`). The whole
  change therefore lives in `ensure_subscriptions_root_and_children`, which runs with the
  key on each visit to the Subscriptions page (`views/subscriptions/page.py`): it adds the
  eight purpose children and then `_prune_empty_cadence_children` removes a default-named
  cadence child that is a leaf and unreferenced. The legacy migration
  `a4e9b2f1c6d8` (pre-encryption, plaintext) is left untouched; the taxonomy seeder adds
  the purpose children for example-data families but does **not** prune (it is not a
  user-facing unlock path).
  `_category_is_referenced` checks every inbound FK across the schema (transaction, split,
  budget, planned transaction, subscription, categorisation rule, reserve fund,
  irregular item, and sub-categories) before a cadence child is removed.

- **Locale of the ensured children** (found in review): the children carry stored names, not
  i18n keys (the taxonomy seed does the same), so they have one language. The service default
  is English; the Subscriptions view passes `CategoryService.default_purpose_children(language)`
  (`app.storage.user["language"]`), so a Polish family gets the Polish purpose names. To
  avoid a doubled tree, `ensure_...` adds nothing when the tree *already* holds a purpose
  child in **any** locale — detected by the purpose names unique to the new scheme, i.e. both
  locales minus the shared `Other`/`Inne`. So a family that switches language keeps its
  existing tree rather than gaining a second, and an example-data (Polish) tree is not
  doubled with English when the page opens.

### Decisions (Part B — filing)

- **The dialog's category select *is* the purpose child.** Part A kept the edit
  dialog's category select on all expense categories; Part B narrows it to the
  Subscriptions-tree purpose children (`sub_category_opts`). One concept, one
  column (Part A): the subscription's `category_id` is its purpose child, and the
  "By category" card already groups by it. The old all-expense `category_opts`
  path is removed from the page and the dialog.
- **Re-filing is generalised from the candidate flow.** `_recategorise_matching`
  (candidate) now delegates to a shared `_recategorise(payee_id, merchant_name,
  amount, …, dry_run)`. Two public methods use it for an existing subscription:
  `refile(sub_id, category_id)` sets the purpose child and moves the matching
  charges (same payee or merchant-key + amount bucket, in the detector window);
  `count_refilable(...)` is the dry run that counts only the charges that would
  actually move (not already under the target), writing nothing.
- **Editing confirms the move.** Saving an edit that changes the purpose child
  runs the dry-run count; if any charges would move, a confirmation ("Move N
  charges to X?") offers to re-file the history or skip. The subscription's own
  filing is saved either way (`update` set it); skip just leaves the history.
- **A curated merchant → purpose map suggests the child.** `suggest_purpose_index`
  matches a curated token list against the uppercased merchant key and returns a
  purpose *index* aligned with `SUBSCRIPTION_PURPOSE_CHILDREN` (EN) and its Polish
  twin; `SubscriptionService.purpose_child_index_map` resolves that index to the
  tree's own child id, so it works whichever language the tree is in. The track
  dialog pre-selects the suggestion; the user can change it. A renamed child
  matches no index and is simply never suggested. The merchant-key keeps only the
  first `/`-segment (bank-description quirk), so some merchants (e.g. iCloud via
  "APPLE.COM/BILL") stay unmatched — acceptable, the user picks.
- BDD: KAL-SUB-007 (re-filing, incl. dry-run) and KAL-SUB-008 (suggestion),
  `@automated` by the integration + unit tests.

#### Known limitations (Part B, from review)

- **A legacy filing outside the tree shows an empty select.** A subscription
  filed under an ordinary expense category (not a purpose child) has no matching
  option, so the select reads empty; saving untouched keeps that category and
  offers no re-file. Safe, but the old filing is invisible until the user picks a
  purpose child. Not worth a dynamic "current category" option yet.
- **A hand-typed name may not match the bank key.** For a payee-less subscription,
  re-filing matches `merchant_key_from_description(sub.name)` against the charges'
  description key; a display name like "Netflix" that differs from the stored bank
  description ("NETFLIX /AMSTERDAM" → "NETFLIX" matches, but a cleaned-up name may
  not) can silently match nothing. Payee-based subscriptions are unaffected.
- **`refile` vs `count_refilable` counts.** `count_refilable` (the confirmation
  number) counts only charges that would actually move; `refile` returns every
  matching charge, including ones already under the target. The view uses only the
  dry-run count, so the number the user sees is the number that moves.

## Implementation

Landed on 2026-10-12 (PR #231).

| SHA | Author | Date | Message |
|---|---|---|---|
| `30c0fb7` | Dawid Adamski | 2026-10-12 | Merge pull request #231 from DawidAdamski/feat/subscriptions-filing |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/subscriptions-categories.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/services/subscription_service.py
- src/kaleta/views/subscriptions/dialogs.py
- src/kaleta/views/subscriptions/page.py
- tests/integration/test_subscription_categories.py
- tests/unit/services/test_subscription_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Part A (the purpose tree) landed earlier; Part B (filing under a purpose child, re-file history, merchant suggestion) landed in PR #231 (feature commits `057c75f`, `a7608f1`). The changed files (subscription service, subscriptions views, locales, tests) were checked against the plan by hand; the automatic Touchpoints match did not recognise them.
