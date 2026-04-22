---
plan_id: wizard-subscriptions
title: Wizard — Subscriptions section
area: wizard
effort: large
status: draft
roadmap_ref: ../product/financial-wizard.md#3-subscriptions
---

# Wizard — Subscriptions section

## Intent

The "Subscriptions" wizard section exists as a placeholder today
(4 empty steps shipped with the collapsible onboarding change). Make
it real: detect subscriptions from transaction history, let the user
manage them, flag renewals, and surface cost-trend insights.

## Scope

- **Detector** (`sub_tracker` step) — scans transactions for
  recurring charges (same payee + similar amount at a cadence of
  ~30 ± 3 days or ~365 ± 14 days). Presents candidates; user
  confirms to create a `Subscription` record.
- **Renewals** (`sub_renewals` step) — shows upcoming charges in the
  next 30 days with estimated amounts; supports "mute for next
  cycle" and "cancel" workflow (cancel marks subscription inactive
  from a user-set date).
- **Audit** (`sub_audit` step) — flags:
  - overlapping services (two music streams, two clouds),
  - subscriptions inactive for 90+ days on the card but still
    charging,
  - auto-renewals with a "long unused" heuristic.
- **Cost trends** (`sub_cost_trends` step) — monthly total cost of
  subscriptions over last 12 months, with a YoY delta.

Also:
- **Detection rules** combine category (new "Subscriptions" seed
  category) and tag (`subscription` from the tags seed plan).
- **Auto-tagging**: when a transaction matches a known subscription
  payee, auto-apply the `subscription` tag and link the tx to the
  `Subscription` record.

Out of scope:
- Actual cancellation via third-party APIs.
- Shared / family plan cost splitting.

## Acceptance criteria

- Running the detector on a seeded DB surfaces plausible candidates
  for known monthly charges (Netflix, Spotify, iCloud patterns).
- Confirming a candidate creates a `Subscription` with payee,
  amount, cadence, first_seen_at, next_expected_at.
- Renewals panel lists the next 30 days sorted by date.
- Audit panel surfaces at least the three rule types, each with a
  one-click resolve action.
- Cost-trends chart renders 12 months with a clear YoY delta.

## Touchpoints

- New model `Subscription` — payee_id, category_id, amount,
  cadence_days, first_seen_at, next_expected_at, status.
- Alembic migration.
- `src/kaleta/services/subscription_service.py` — detector, renewal
  predictor, audit rules, cost-trend query.
- `src/kaleta/services/transaction_service.py` — auto-tagging hook
  after a transaction is created/updated.
- `src/kaleta/views/wizard.py` — 4 subscription steps become real
  panels.
- Seed: add "Subscriptions" category and ensure `subscription` tag
  exists (depends on `tags-seed-list` plan).
- `src/kaleta/i18n/locales/*`.

## Open questions

- Cadence tolerance: ±3 days for monthly, ±14 days for yearly. Tune
  after dogfood.
- Amount tolerance: ±5% absolute, or a fixed 2 PLN? Start with 5%.
- Detector scope: last 12 months only to avoid noise from legacy
  data.

## Implementation notes

_(filled as work progresses)_
