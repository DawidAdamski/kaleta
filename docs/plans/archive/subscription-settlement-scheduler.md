---
plan_id: subscription-settlement-scheduler
title: Settle due subscription cancellations on a schedule, not only on page open
area: subscriptions
effort: small
status: archived
archived_at: 2026-10-24
roadmap_ref: ../../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Settle due subscription cancellations on a schedule, not only on page open

Origin: chore `docs/plans/chores.md:287`, found by
`plan/subscriptions-panel-gaps`.

## Intent
A subscription cancellation scheduled for a future date only flips from
active to `cancelled` when `SubscriptionService.settle_due_cancellations`
runs. Today that happens only on opening `/wizard/subscriptions`. Until
someone opens that page, every reader that filters on
`status != CANCELLED` keeps counting the subscription as active even though
its cancellation date has passed:

- the unplanned radar,
- the detector's tracked-payee / tracked-merchant set (so a cancelled
  payee keeps suppressing its candidate),
- `GET /api/v1/subscriptions`.

The fix runs settlement at startup and once per day across every active
tenant schema, so the flip no longer waits for a human to visit the panel.

## Scope
- New `SubscriptionSettlementScheduler` in
  `src/kaleta/services/subscription_settlement_scheduler.py`, a near-copy
  of `EventRetentionScheduler`: `start`/`stop`/`_loop`/`_settle_once`/
  `_settle_current`, a `_task` class attr, a 24h interval constant. One
  sweep visits every active family's schema (registry layout); a suspended
  family is skipped; one family failing does not stop the others.
- Register it in `src/kaleta/main.py` beside `EventRetentionScheduler`
  (`run_web` helper + `_api_lifespan`).
- No feature flag to gate on — settlement is always wanted, so `start()`
  starts unconditionally (keeping the "no running loop" and "already
  running" guards).

Not in scope:
- `settle_due_cancellations` itself is unchanged — it is already
  idempotent (a second run matches no rows) and commits its own session.
- The `/wizard/subscriptions` call site stays (a harmless extra settle).
- No view changes.

## Acceptance criteria
- `uv run pytest tests/integration/test_subscription_settlement_scheduler.py -q`
- `uv run pytest tests/integration/test_event_retention_families.py tests/integration/test_subscriptions_panel.py tests/unit/services/test_subscription_service.py -q`
- `uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `grep -q "KAL-SUB-010" docs/bdd.md`

## Touchpoints
- `src/kaleta/services/subscription_settlement_scheduler.py` (new)
- `src/kaleta/main.py`
- `docs/bdd.md` (KAL-SUB-010)
- `tests/integration/test_subscription_settlement_scheduler.py` (new)

## Open questions
None.

## Implementation notes
- `settle_due_cancellations` commits itself (only when `due` is non-empty),
  so `_settle_current` mirrors the wizard call site exactly: open a session,
  `await SubscriptionService(session).settle_due_cancellations()`, no extra
  commit. The retention `_purge_current` likewise relies on its services'
  own commits.
- Idempotent: the query filters `status != CANCELLED`, so a second sweep
  matches nothing and returns 0 without committing.
- The integration test mirrors `test_event_retention_families.py`: a
  multi-tenant sweep across two active families plus one suspended family,
  asserting the suspended one is skipped.

### Landed

- Commit: `80676f5` (PR #370), author Dawid (Ani), merged 2026-10-24.
- Files touched:
  - docs/bdd.md
  - src/kaleta/main.py
  - src/kaleta/services/subscription_settlement_scheduler.py
  - tests/integration/test_subscription_settlement_scheduler.py

## Implementation (filled by plan-archiver)
