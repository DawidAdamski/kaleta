---
plan_id: wizard-subscriptions
title: Wizard — Subscriptions section
area: wizard
effort: large
status: archived
archived_at: 2026-04-23
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

## Implementation

Landed on 2026-04-23.

| SHA | Author | Date | Message |
|---|---|---|---|
| `96f4830` | Dawid | 2026-04-23 | feat(wizard): Subscriptions — detector, renewals, tracking |

**Files changed:**
- `src/kaleta/models/subscription.py` (new — Subscription + SubscriptionStatus StrEnum)
- `src/kaleta/models/__init__.py` (exports)
- `alembic/versions/e7c4b1a3d9f2_add_subscriptions.py` (new migration, down_revision f2a8c4d1e5b7)
- `src/kaleta/schemas/subscription.py` (new — SubscriptionCreate/Update/Response, DetectorCandidate, RenewalRow, SubscriptionTotals)
- `src/kaleta/services/subscription_service.py` (new — CRUD + mute/cancel/reactivate + detect_candidates + create_from_candidate + upcoming_renewals + totals)
- `src/kaleta/services/__init__.py` (exports)
- `src/kaleta/views/subscriptions.py` (new — `/wizard/subscriptions` page)
- `src/kaleta/main.py` (registers view)
- `src/kaleta/views/wizard.py` (_STEP_ROUTES maps sub_tracker/sub_renewals/sub_audit/sub_cost_trends → /wizard/subscriptions)
- `src/kaleta/i18n/locales/en.json` (new subscriptions.* block — ~45 keys)
- `src/kaleta/i18n/locales/pl.json` (new subscriptions.* block — ~45 keys)
- `tests/unit/services/test_subscription_service.py` (18 tests: CRUD, status transitions, totals, detector, renewals)

**What shipped:**
- Subscription model with payee/category FKs, amount + cadence_days, first_seen_at/next_expected_at, status enum (active/muted/cancelled), muted_until/cancelled_at, url, auto_renew.
- Detector: scans last 365 days of non-transfer expense tx; groups by (payee, amount-bucket); cadence inferred from average gap — monthly (30±5d) or yearly (365±21d); excludes payees already tracked (active or muted subs); needs ≥2 occurrences; sorts candidates by amount desc.
- create_from_candidate creates a Subscription and projects next_expected forward past today so the new row shows up in Upcoming Renewals even when last charge was >cadence days ago.
- Upcoming renewals (30 days) filters active subs with next_expected_at in window.
- Totals (monthly + yearly) normalise yearly subs via amount × 30 / cadence_days.
- View has header with active count + total-monthly/yearly badges, Add-subscription dialog (reusable for Edit), 3 stacked cards (Detector / Renewals / All subscriptions), per-row Edit/Mute/Cancel/Reactivate/Delete actions, delete-confirm dialog.
- Wizard step-row links all 4 subscription keys to `/wizard/subscriptions`.

**Partial coverage / deferred:**
- `sub_audit` step (overlapping services, inactive 90+ days, auto-renew long-unused heuristic) — not shipped. No audit rules engine yet. All 4 wizard keys land on the same page; the audit card is the obvious next addition.
- `sub_cost_trends` step (12-month chart with YoY delta) — not shipped. Only the scalar monthly + yearly totals are surfaced in the header. A chart would need ECharts wiring.
- TransactionService auto-tagging hook — not shipped. New transactions matching a tracked payee do not auto-apply the `subscription` tag yet.
- Seed data — `scripts/seed.py` not updated with a "Subscriptions" category or sample subs; user confirms real candidates from their own history (validated in browser — 18 real recurring payees surfaced on the dev DB).
- Detector tolerance tuning — plan called for ±3d / ±14d; v1 uses ±5d / ±21d (more forgiving — weekends shift charges). Retune after dogfood.
- Subscription grouping taxonomy (streaming/SaaS/memberships) — not shipped. v1 uses the existing category_id FK; no SubscriptionGroup table.
- Management URL field exists on the model + form but has no "Open" button on the row yet — pure data until then.
