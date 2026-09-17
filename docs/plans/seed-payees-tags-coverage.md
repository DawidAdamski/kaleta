---
plan_id: seed-payees-tags-coverage
title: Seed — payees and tags coverage in example data
area: seed
effort: small
roadmap_ref: ../roadmap.md#seed
status: in-progress
deferred_to: q4-2026
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
_Filled in as work progresses._
