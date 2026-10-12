---
plan_id: subscriptions-categories
title: Subscriptions by what they are — streaming, software, phone — not by how often they bill
area: subscriptions
effort: medium
status: draft
roadmap_ref: ../roadmap.md#subscriptions
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
