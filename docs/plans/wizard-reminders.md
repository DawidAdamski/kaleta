---
plan_id: wizard-reminders
title: Wizard — notifications and reminders across all sections
area: wizard
effort: large
roadmap_ref: ../product/financial-wizard.md#shared-wizard-patterns
status: draft
---

# Wizard — notifications and reminders across all sections

## Intent

The Financial Wizard deep-dive describes **every section supports
reminders** — Monthly Readiness nudges the user to plan the next
month, Subscriptions prompts periodic reviews, Safety Funds
reminds of missed transfers, Personal Loans nudges as return dates
approach. None of that infrastructure exists yet. Each section
implements its own in-page prompt, but there is no out-of-app
reminder (email, messenger, in-app push) and no central place to
see pending nudges.

Ship a cross-cutting notifications system: one `Notification`
entity with a type, target date, and delivery channel, plus
per-section producers that emit notifications and a shared
dispatcher that delivers them. Settings gets a per-channel config
block.

## Scope

- **Model**: new `Notification` table —
  `id`, `kind` (`monthly_readiness_plan` | `subs_review` |
  `funds_missed_transfer` | `loan_due_soon` | `loan_overdue` |
  `custom`), `title`, `body`, `target_date` (when it should fire),
  `fired_at` (nullable), `delivered_via` (set of channels),
  `dismissed_at` (nullable), `source_kind` (which entity produced
  it: `planned_transaction` / `subscription` / `personal_loan` /
  `reserve_fund` / `system`), `source_id`, `user_id` (nullable in
  single-user MVP but reserved for multi-user future),
  `created_at`.
- **Producer hooks**:
  - Monthly Readiness: emit a `monthly_readiness_plan` reminder
    N days before month-end (configurable; default 5).
  - Subscriptions: emit `subs_review` every N months (default 3).
  - Safety Funds: emit `funds_missed_transfer` if the monthly
    transfer planned date has passed without a matching
    transaction (default 2 days late).
  - Personal Loans: emit `loan_due_soon` 7 days before
    `expected_return_date`, `loan_overdue` the day after.
  - Producers run on a daily scheduler (lightweight cron — see
    below).
- **Scheduler**: an `apscheduler` `BackgroundScheduler` (already a
  compatible dependency; confirm) running one job daily at a
  configurable hour (default 07:00 local). The job calls
  `NotificationService.run_producers()` which executes every
  producer and upserts notifications.
- **Delivery channels** (off-the-shelf for v1):
  - `in_app` — in-app bell icon in the top-right of every page,
    opens a drawer listing unread notifications.
  - `email` — SMTP; per-user from-address, smtp host, port,
    credentials stored in Settings.
  - `messenger` — generic outbound webhook URL (Discord, Slack,
    Telegram via bot); POST JSON `{title, body, source_url}`.
- **Settings** — new tab "Notifications" with:
  - Channel toggles (in-app / email / messenger).
  - SMTP host / port / credentials / from-address (email).
  - Webhook URL (messenger).
  - Per-kind schedule (how many days ahead / cadence).
  - Quiet hours (no delivery between HH:MM and HH:MM).
- **UI: bell icon + drawer** — in the top header, next to the
  theme toggle. Badge with unread count. Drawer lists
  notifications grouped by date, each with title + body + link
  to the source page + "mark read" / "dismiss" actions.
- **API**: `/api/v1/notifications` — list (filterable by
  `fired_at`, `dismissed_at`, `kind`), mark-read, dismiss.
- **Paid-tier AI-generated narratives** are **out of scope**
  (mentioned in the deep-dive as paid-tier); stub the channel but
  don't build the AI producer.
- **Unit tests** — every producer; the scheduler's daily job
  (tested with mocked clock); dispatcher per channel (SMTP
  mocked, webhook mocked).

Out of scope:
- True push notifications (browser Notifications API / service
  worker push) — future plan.
- Per-category / per-merchant alerts.
- Backfill of existing due dates — producers generate
  notifications only from when the system is enabled.
- Internationalised delivery content beyond the EN / PL keys.
- Rate-limit / batching — deliver one notification per event.

## Acceptance criteria

- Creating a `PersonalLoan` with `expected_return_date` 7 days
  from now and toggling notifications on produces a
  `loan_due_soon` notification after the daily job fires.
- The in-app bell shows the badge count and the notification in
  the drawer; clicking the link routes to `/personal-loans`.
- Enabling email with a valid SMTP config delivers the same
  notification to the configured address (verifiable via a
  mocked SMTP in tests; manual verification via a test SMTP
  locally).
- Enabling the messenger webhook posts JSON with the title,
  body, and source URL to the configured webhook.
- Dismissing a notification hides it from the drawer; the same
  reminder is *not* re-emitted for that event within its cadence
  window.
- Quiet hours delay delivery until the window closes (channel
  retries next run).
- The daily scheduler runs without blocking the web server; a
  failure in one producer doesn't halt the others.

## Touchpoints

- New files:
  - `src/kaleta/models/notification.py`
  - `src/kaleta/schemas/notification.py`
  - `src/kaleta/services/notification_service.py`
    (includes producer registry + channel dispatchers).
  - `src/kaleta/services/scheduler_service.py` — apscheduler setup.
  - `alembic/versions/NNN_add_notifications.py`.
  - `src/kaleta/api/v1/notifications.py`.
- Touched files:
  - `src/kaleta/main.py` — start scheduler in `run_web` /
    `run_app` (not `run_api`).
  - `src/kaleta/views/layout.py` — add bell icon + drawer.
  - `src/kaleta/views/settings.py` — new Notifications tab.
  - `src/kaleta/i18n/locales/{en,pl}.json` — ~40 new keys.
  - `pyproject.toml` — add `apscheduler` if not present; confirm.

## Open questions

1. **Scheduler vs. lazy-on-request** — run the daily job from
   apscheduler, or on every page load if `last_ran_at` is stale?
   Default: **apscheduler** for reliability and low per-request
   cost.
2. **SMTP password storage** — plain text in `app.storage.user`
   or encrypted at rest? Default: **env var fallback + plain in
   storage** (MVP); separate plan for encrypted credentials.
3. **Webhook format** — free-form JSON vs. Slack-compatible
   payload? Default: **generic `{title, body, source_url}`**;
   Slack users can receive it via Slack's "incoming webhook"
   which accepts arbitrary JSON in the `text` if the user
   configures their webhook accordingly.
4. **Unsubscribe per kind** — a user can keep `loan_due_soon` on
   but turn `subs_review` off. Default: **yes**, per-kind toggle
   in the Settings panel.
5. **Persistence of delivered-and-dismissed notifications** —
   keep forever or prune after 90 days? Default: **prune after
   90 days** via a daily housekeeping job.

## Implementation notes
_Filled in as work progresses._
