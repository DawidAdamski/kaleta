---
plan_id: seed-payees-tags-coverage
title: Seed — payees and tags coverage in example data
area: seed
effort: small
roadmap_ref: ../roadmap.md#seed
status: in-progress
---

# Seed — payees and tags coverage in example data

## Intent

`scripts/seed.py` seeds 6 years of transactions and the canonical tag
list, but **no `Payee` rows** and **no transaction → tag links** are
created. As a result a fresh demo install renders an empty Payees
page, an empty "By payee" report, and tag chips never appear in the
transactions list. The seed should ship with realistic Polish payees
attached to most expense rows and a sensible tag fan-out so every
panel that consumes payees / tags has data to render.

## Scope

- **Payees** — add a curated list of ~25 realistic Polish merchants
  spanning the major expense categories:
  - Groceries: *Biedronka*, *Lidl*, *Carrefour*, *Żabka*, *Auchan*.
  - Restaurants/cafés: *Pasibus*, *Costa Coffee*, *Da Grasso*,
    *Sphinx*, *Starbucks*.
  - Transport/fuel: *Orlen*, *Shell*, *BP*, *MPK Warszawa*,
    *Uber*, *Bolt*.
  - Utilities/rent: *PGNiG*, *Tauron*, *Veolia*, *MPWiK*,
    *Wspólnota Mieszkaniowa*.
  - Pharmacies/health: *Apteka Gemini*, *Apteka DOZ*, *Medicover*.
  - Subscriptions: *Netflix*, *Spotify*, *YouTube Premium*,
    *iCloud*, *ChatGPT Plus*.
  - Online: *Allegro*, *Amazon.pl*, *Empik*.
- Map each merchant to one or more **categories** (the seed already
  has `cat_by_name`); when generating an expense in a mapped
  category, pick from the matching pool of payees, with a small
  random chance of leaving `payee_id=None` (to mirror real data).
- For categories without a curated pool (e.g. "Inne wydatki"), fall
  back to `fake.company()` for ~30% of transactions and leave the
  rest payee-less.
- **Tags** — extend `add_tx` so that:
  - Card account → attach `Card`.
  - Cash account → attach `Cash`.
  - Credit account → attach `Card`.
  - Online merchants (Allegro / Amazon / Netflix / Spotify / etc.) →
    additionally attach `Online`.
  - Subscriptions root descendants → additionally attach
    `Subscription` and `Recurring`.
  - Internal transfers → already conceptually `Transfer`; attach
    the canonical `Transfer` tag to both legs.
  - Random ~10% chance to attach `Refundable` on Restaurants,
    Electronics or Online expenses, simulating receipts that may
    be returned.
- Backfill the `transaction_tag` association table by appending
  to `tx.tags` before `session.add_all`.

Out of scope:
- Auto-detection of payees from descriptions during seed — payees
  are picked explicitly.
- Custom tags beyond the eight canonical ones.
- Adjusting the tag migration / model — uses the existing
  many-to-many.
- Per-payee subscription seed entries — covered by the existing
  Subscriptions panel which derives from category tree.

## Acceptance criteria

- After `uv run python scripts/seed.py`, the Payees page lists
  roughly 25 named payees, each with at least a few attached
  transactions.
- The "By payee" report (or any report grouping by payee) is
  non-empty.
- A spot-check on the Transactions table shows tag chips on
  most rows: at minimum a `Card` / `Cash` chip for every
  expense.
- All transfer pairs carry the `Transfer` tag.
- All Subscription-root descendants carry `Subscription` +
  `Recurring`.
- Seed completes in roughly the same time as today (no order-
  of-magnitude slowdown).

## Touchpoints

- `scripts/seed.py` — main work:
  - new `Payee` block, near the existing tag block.
  - new `cat_to_payees` map for the merchant pools.
  - `add_tx` gains optional `payee=` and `tags=` kwargs.
  - tag fan-out logic in the per-month loop.
- `src/kaleta/models/payee.py` — read-only reference; no schema
  change needed.
- `README.md` — bump the demo summary ("…with N payees, M tagged
  transactions").

## Open questions

1. **How many merchants per category?** Default: 3–5 per major
   category, 1 per minor.
2. **Random payee assignment frequency** — every expense, or
   ~70%? Default: **70%**, leaving 30% payee-less so the empty
   case is still represented in demo data.
3. **Do we want tag fan-out for income rows too?** Default: no —
   income tags are noise in demo data.
4. **Stable `random.seed(42)` distribution** — ensure the seeded
   data is deterministic across runs (already true thanks to the
   global seed at the top of the file).

## Implementation notes

### Open questions — resolved with the plan defaults

1. **Merchants per category** — the curated pools are exactly the ones
   listed in Scope, grouped per expense category: 5 groceries, 5
   restaurants, 3 transport, 3 fuel, 4 utilities, 1 rent, 3 health, 5
   subscriptions, 3 online (reused across Elektronika / Rozrywka /
   Odzież). 32 curated names + 5 generated ones = 37 payees.
2. **Payee assignment frequency** — default taken: `PAYEE_ASSIGN_CHANCE
   = 0.70` for curated categories, `FALLBACK_PAYEE_CHANCE = 0.30` for
   the rest. 744 of ~1527 rows end up with a payee.
3. **Tag fan-out for income** — default taken: none. Income rows carry
   no tags, asserted by KAL-PLT-004.
4. **Determinism** — the default asked for it, and it turned out the
   file only had half of it: `random.seed(42)` pins the stdlib module,
   but Faker draws from its own `Random`, so `fake.company()` /
   `catch_phrase()` / `city()` were never pinned. Since the generated
   payee names are now persisted under a unique constraint, the seed
   script now also calls `Faker.seed(42)`. Two consecutive runs produce
   byte-identical payee names and descriptions. Adding the new
   `random.*` calls shifted the sequence once; it is stable from here.

### Decisions

- **Fallback merchants are a fixed pool, not one per call.** The plan
  says to fall back to `fake.company()`; calling it per transaction
  would create hundreds of one-transaction payees and break "roughly 25
  named payees, each with a few transactions". Instead five company
  names are generated once (deduped against the curated names, since
  `Payee.name` is unique) and reused.
- **Every non-cash expense gets `Card`.** Scope names a "Card
  account", a "Cash account" and a "Credit account", but `AccountType`
  has no `CARD` member: the seeded accounts are CHECKING, SAVINGS, CASH
  and CREDIT. So the rule is by payment method — CASH → `Cash`,
  everything else (CHECKING, CREDIT) → `Card` — which is what the
  acceptance criterion "a `Card` / `Cash` chip for every expense" asks
  for.
- **Two categories are named "Subskrypcje".** The seed creates a flat
  one from `EXPENSE_CATEGORIES` (used by the budgets and the random
  expense loop) *and* the `is_subscriptions_root` tree. Only the flat
  one ever receives transactions, so `subscription_cat_ids` covers
  both it and the root's descendants — otherwise the
  `Subscription` / `Recurring` rule would never fire. Moving the
  transactions under the tree instead would have emptied the
  "Subskrypcje" budget line, which is out of scope here. The duplicate
  itself is pre-existing and left alone.
- **Transactions are added to the session as they are built.** Tags are
  already persistent when they are attached, so appending to a detached
  transaction's collection emitted `SAWarning: Object of type
  <Transaction> not in session` and would silently drop the link. The
  bulk `session.add_all(all_tx)` at the end is therefore gone.
- **Summary counters are kept as the rows are built.** Reading
  `tx.tags` back after the loop would trigger a lazy load from sync
  code (`MissingGreenlet`).
- **Descriptions are untouched.** Naming the payee in the description
  would be payee→description inference in reverse and is out of scope;
  it would also interact with the demo `LIDL` categorisation rule.
- Seed runtime is unchanged: 1.19 s before, 1.04 s after (local,
  SQLite).

### Coverage

`KAL-PLT-003` (payees) and `KAL-PLT-004` (tags) are new in
`docs/bdd.md`, both `@automated` by
`tests/integration/test_seed_payees_tags.py`, which runs the real
`scripts/seed.py` against a throwaway SQLite file once per module and
asserts on the resulting rows.

### Left for the owner

The "spot-check the Transactions table / Payees page / by-payee report
in the UI" half of the acceptance criteria is manual — the automated
test asserts the same facts at the database and service level.
