---
plan_id: bug-reports-and-logging
title: Bug reports from the app, and structured logs to read them by
area: observability / settings
effort: medium
status: archived
archived_at: 2026-09-22
roadmap_ref: ../../roadmap.md#cross-cutting-principles
---

# Bug reports from the app, and structured logs to read them by

## Intent

Today a failure shows an Event ID in a toast and the user is expected
to find GitHub and paste it. The event holds a stack trace but no
words from the user, and the server log is unstructured text with no
way to correlate a line with an event, a request or a tenant. This
plan adds an in-app "Report a problem" flow that attaches the right
diagnostics with the user's explicit consent, routes reports to the
maintainer without a third-party error service, and turns the logs
into structured JSON with correlation ids so an event id leads to the
lines around it. It builds on `app_events`
([observability-anonymous-events](observability-anonymous-events.md))
and respects the encryption promise of
[ADR-35](../../adr/035-hosted-multi-tenancy-and-user-held-encryption.md):
nothing from the ledger ever leaves the tenant unless the user types it
into the report.

## Scope

### 1. Structured logging (`kaleta/logging_config.py`)

- `KALETA_LOG_FORMAT=text|json` (default `text` for a terminal, `json`
  when `KALETA_TENANCY=multi`), `KALETA_LOG_LEVEL` (default `INFO`),
  stdout only — the host (Podman `journald`, Fly/Railway log drain)
  ships it. Stdlib `logging` with a small `JsonFormatter`; no new
  dependency.
- Every record carries `ts`, `level`, `logger`, `msg`, `request_id`,
  `tenant_id` (never the e-mail), `session_id`, `route`, `app_version`,
  and `event_id` when one was issued in that request. Values come from
  a `ContextVar` set by a `RequestContextMiddleware` (accepts an
  incoming `X-Request-ID`, generates one otherwise, returns it in the
  response) and, for NiceGUI page handlers, from the client context.
  The existing `RequestLoggingMiddleware` merges into it.
- `RedactingFilter` on the root logger: drops or masks query strings,
  `Authorization` headers, anything matching the bearer-token prefix,
  e-mail addresses, and any argument longer than 200 characters (the
  audit-log JSON blobs are the usual offender). Log calls in `src/`
  that pass descriptions, payee names or account numbers are found and
  removed in this plan (`grep -n "description\|payee\|account_number"`
  across `logger.` calls; list the hits in implementation notes).
- Per-session **ring buffer**: the last 200 redacted records for the
  current `session_id`, held in memory (a `deque` per session, dropped
  with the session). This is what a bug report can attach.
- `AppEvent.request_id` already exists; the capture path fills it from
  the context so `event_id ↔ request_id` join works in logs.

### 2. Bug report model and service

- New model `BugReport` — in `single` mode a tenant table, in `multi`
  mode in `public` (reports are operator data, and a report must be
  readable while the tenant is locked): `id`, `report_id` (short public
  id like `event_id`), `created_at`, `tenant_id` / `user_id`,
  `contact_email` (nullable; hosted defaults to the account e-mail,
  self-hosted optional), `summary` (≤ 120 chars), `description` (text),
  `event_ids` (JSON list), `route`, `app_version`, `user_agent`,
  `viewport`, `locale`, `log_excerpt` (nullable, the ring buffer as
  JSON, only when the box is ticked), `status`
  (`new|seen|closed`), `external_ref` (GitHub issue URL when one is
  opened).
- `BugReportService`: `create(...)`, `list(status)`, `mark(status)`,
  `attach_external_ref`. Retention: `KALETA_BUG_REPORT_RETENTION_DAYS`
  (default 90), reaper folded into `EventRetentionScheduler`.
- Delivery, all optional and env-driven, executed after commit and never
  blocking the UI:
  - `KALETA_BUG_REPORT_WEBHOOK` — `POST` the report JSON (no
    `log_excerpt` unless `KALETA_BUG_REPORT_WEBHOOK_INCLUDE_LOGS=true`)
    to an n8n / generic endpoint. This is the maintainer's route for the
    hosted instance: n8n turns it into an e-mail, a chat message or a
    GitHub issue.
  - `KALETA_BUG_REPORT_EMAIL` + SMTP settings — a plain e-mail for
    self-hosters who run their own instance for family and want to
    hear about problems.
  - "Open a GitHub issue" button in the confirmation dialog: prefilled
    `https://github.com/DawidAdamski/kaleta/issues/new?template=bug.yml&title=…&body=…`
    with summary, event ids, version and route — never the log excerpt
    or the description, which may contain what the user chose to type.
    Add `.github/ISSUE_TEMPLATE/bug.yml` with a `report_id` field.

### 3. Report a problem — UI

- Entry points: the error toast (`views/error_handling.py`) gains a
  "Report" action next to the Event ID; Settings → Privacy & diagnostics
  gets a "Report a problem" button; the sidebar help menu links to the
  same dialog.
- Dialog: summary, "what were you doing?" (textarea), the event ids
  collected in this session (chips, removable), a read-only block
  showing exactly what will be sent (version, route, browser,
  viewport, locale), a checkbox "Attach the last 200 log lines from
  my session (redacted — no amounts, names or descriptions)" default
  off, and the sentence "We never attach your financial data. Only
  what you write here leaves your account." Submit → confirmation with
  the `report_id`, the GitHub button and "copy report id".
- Rate limit: 5 reports per session per hour.
- i18n `bugreport.*`; a `KAL-BUG-*` BDD area.

### 4. Maintainer side

- `scripts/bug_reports.py list|show <id>|close <id>` over the
  configured database (public schema in `multi`), printing the log
  excerpt as a readable table with the event's stack trace joined from
  `app_events`.
- `docs/privacy.md` (or `privacy-events.md` until the rollout plan
  renames it) gains a "Bug reports" section: what a report contains,
  that the description is unencrypted operator data, retention, how to
  ask for deletion.
- Settings → Privacy shows the user's own reports (`report_id`, date,
  status) with "delete" — the user can always withdraw one.

### 5. Optional error-tracker hook (behind a flag, not a dependency)

- `KALETA_ERROR_TRACKER_DSN`: when set, `event_capture` also forwards
  the event (class, redacted trace, version, route, `event_id`) to a
  Sentry-protocol endpoint — GlitchTip self-hosted on the home k3s
  cluster is the intended target, Sentry SaaS would work the same.
  Implemented with `sentry-sdk` in a new `tracker` extra and a
  `before_send` that strips everything except the fields the
  anonymous event already holds. Default off; `docs/privacy.md` says
  when it is on for the hosted instance.

### Not in scope

- Metrics / tracing (OpenTelemetry) — a later plan once there is a
  second replica or a real latency question.
- Screenshots or screen recording in reports.
- Client-side (browser) error capture — NiceGUI renders on the server;
  the useful failures are server-side.
- Shipping logs to a hosted aggregator (Loki, Better Stack) — the JSON
  format is the interface; the host does the shipping.

## Acceptance criteria

- `uv run pytest tests/unit/test_logging_config.py -q` — JSON records
  carry the context fields; redaction masks bearer tokens, e-mails,
  query strings and long arguments; ring buffer capped at 200 and
  dropped with the session
- `uv run pytest tests/unit/services/test_bug_report_service.py -q` —
  create/list/mark, retention reaper, webhook payload excludes
  `log_excerpt` by default, delivery failures never surface to the UI
- `uv run pytest tests/integration/test_bug_report_api_context.py -q`
  — an API error yields `event_id` and `request_id` that appear in the
  same JSON log line
- `uv run pytest tests/e2e/test_bug_report.py -q` — trigger a seeded
  `500`, click Report in the toast, submit, see the `report_id`; the
  report row holds the event id and no log excerpt
- `test -f .github/ISSUE_TEMPLATE/bug.yml`
- `grep -rn "print(" src/kaleta | grep -vc "# noqa" | grep -q '^0$'`
- `uv run python scripts/spec_coverage.py`
- `grep -c "KAL-BUG-" docs/bdd.md | grep -qE '^[1-9]'`
- `./scripts/verify.sh --e2e`
- `[manual]` Point `KALETA_BUG_REPORT_WEBHOOK` at an n8n webhook, file
  a report, confirm the flow that turns it into a GitHub issue and an
  e-mail; read the log excerpt with `scripts/bug_reports.py show`.

## Touchpoints

`src/kaleta/logging_config.py`, `src/kaleta/observability/{context,redact,ring_buffer}.py`
(new; sits with `kaleta.config` in the import-linter layers),
`src/kaleta/models/bug_report.py` (new), `alembic/versions/<new>_bug_reports.py`
(+ `alembic_public/` when `multi`), `src/kaleta/services/bug_report_service.py`
(new), `src/kaleta/services/event_capture.py`, `src/kaleta/services/event_retention_scheduler.py`,
`src/kaleta/main.py` (middleware order), `src/kaleta/views/error_handling.py`,
`src/kaleta/views/bug_report_dialog.py` (new), `src/kaleta/views/settings/privacy_tab.py`,
`src/kaleta/views/layout.py` (help menu), `src/kaleta/config/settings.py`,
`scripts/bug_reports.py` (new), `.github/ISSUE_TEMPLATE/bug.yml` (new),
`src/kaleta/i18n/{en,pl}.json`, `docs/privacy-events.md`,
`docs/tech-stack.md`, `docs/bdd.md`, `pyproject.toml` (`tracker` extra).

## Open questions

- Where should hosted reports land first: the n8n webhook (Dawid's
  existing automation) or straight into GitHub issues via a token held
  by the app? The webhook keeps GitHub credentials out of the app and
  lets the routing change without a deploy — recommended.
- Should the ring buffer include `DEBUG` records when `KALETA_DEBUG` is
  off? Keep it at `INFO`; a maintainer who needs more asks the user to
  reproduce with debug on.
- Self-hosted default for `contact_email`: leave empty; a self-hoster
  reporting to themselves has no use for it, and one reporting upstream
  can type it.
- GlitchTip on the home cluster is an ops choice for the rollout plan,
  not this one; here only the flag and the `before_send` scrubber exist.

## Implementation notes

### Open questions, resolved with the plan's defaults

- **Where hosted reports land first** — the webhook
  (`KALETA_BUG_REPORT_WEBHOOK`), as recommended. No GitHub token lives in
  the app; the confirmation dialog's "Open a GitHub issue" button only
  prefills a form the user submits themselves.
- **Ring buffer level** — `INFO`, as recommended. The `RingBufferHandler`
  is created at `max(root level, INFO)`, so `KALETA_DEBUG=true` does not
  flood a report with `DEBUG` lines.
- **Self-hosted `contact_email`** — left empty; the dialog's field is
  optional and blank by default.
- **GlitchTip** — only the flag (`KALETA_ERROR_TRACKER_DSN`), the
  `before_send` scrubber and the `tracker` extra are here; where it runs is
  an ops choice for the rollout plan.

### Decisions a reviewer should know

- **No tenancy yet.** The plan describes `KALETA_TENANCY=multi` behaviour
  (JSON logs by default, `BugReport` in the `public` schema, a `tenant_id`
  column). `kaleta.config.Settings` has no tenancy knob —
  `hosted-tenancy-foundation` is still `draft` — so `KALETA_LOG_FORMAT`
  defaults to `text` and `bug_reports` is an ordinary tenant table.
  `observability.context` already carries a `tenant_id` field that stays
  `None` until that plan lands.
- **`bug_reports.session_id`** is not in the plan's field list but the
  plan's own rate limit ("5 reports per session per hour") needs it; it is
  the NiceGUI client id, the same opaque value `app_events.session_id`
  already holds.
- **Context survives an escaping exception.** Starlette's 500 handler runs
  *outside* user middleware (`ServerErrorMiddleware` is outermost), so
  `RequestContextMiddleware` deliberately does not reset the context vars
  when an exception propagates — otherwise the event id issued by that
  handler, and the log lines around it, would lose their `request_id`. The
  binding dies with the request task, and every `bind_request` sets all six
  values, so a later request can never read a stale one. For the same
  reason the `X-Request-ID` response header is only added on responses that
  pass back through the middleware (i.e. not on an unhandled 500).
- **Redaction order matters.** Query strings are masked before the
  credential rule: a `?token=…` swallowed by the credential rule first
  would leave the rest of the query in the clear. Covered by
  `test_query_strings_are_dropped_but_the_path_stays`.
- **Filters live on handlers, not loggers.** A `logging.Filter` on the root
  logger does not see records propagated from child loggers, so
  `configure_logging` attaches `RedactingFilter` to each handler — the one
  place every record passes through.
- **Pre-existing bug fixed on the way.** `notify_kaleta_error` created a
  bare `asyncio.create_task`, and NiceGUI 3.x keys its slot stack by
  asyncio task: every `ui.*` call in that coroutine raised "the slot stack
  for this task is empty" and was swallowed with the task. No toast and no
  event was ever produced from a UI `KaletaError`. The coroutine now takes
  the client captured in the caller's task and re-enters it with
  `with client:`. Without this, nothing in section 3 of the plan could
  work.
- **No "Report" button inside the Quasar toast.** `ui.notify` serialises
  its options to the browser as JSON, so a Quasar notify *action* cannot
  carry a Python handler. The toast stays as it was (message + event id)
  and the Report affordance lives in a small fixed **error tray**
  (`views/error_handling.ErrorTray`) shown alongside it whenever an event
  id was issued. Same one-click path, different element.
- **"the sidebar help menu"** — there is no help menu; the header's account
  menu is the only one, so "Report a problem" sits there, above Log out.
- **Debug-only test trigger.** Settings → Privacy & diagnostics shows
  "Trigger a test error" only when `KALETA_DEBUG=true`. It walks the real
  failure path (`notify_kaleta_error`) and is what the e2e scenario uses as
  its seeded `500`.
- **`kaleta.observability` is a new import-linter layer**, between
  `kaleta.db` and `kaleta.config`. `app_version()` moved there so
  `logging_config` and `event_service` share one implementation instead of
  two copies.
- **Retention.** The bug-report reaper is folded into
  `EventRetentionScheduler`, but each purge now has its own switch
  (`KALETA_EVENTS_ENABLED` / `KALETA_BUG_REPORTS_ENABLED`) so turning
  events off no longer silently stops report expiry.
- **`# type: ignore` in `error_tracker.py`** — two, on `import sentry_sdk`,
  the same `[import-not-found,unused-ignore]` form
  `prophet_forecaster.py` already uses for the optional `forecast` extra.
  `sentry-sdk` ships in the new optional `tracker` extra, so it is absent
  from a default dev environment.

- **`alembic/env.py` now passes `disable_existing_loggers=False`.** The app
  runs `alembic upgrade` in-process on startup (`ensure_schema_current`), and
  `fileConfig`'s default disables every logger created before it — i.e. the
  whole application, for the rest of the process. A plan about logs cannot
  leave that in place. It also made
  `tests/integration/test_bug_report_api_context.py` pass or fail depending on
  whether a migration ran earlier in the session.
- **`tests/backup_helpers.seed_every_model`** gained a `BugReport` row: the
  backup round-trip tests assert every table in `Base.metadata` holds at least
  one row, and a new table would otherwise fail them. Reports travel in the
  user's own ZIP export, like `app_events` already do.

### Review findings addressed

- **Bearer tokens.** The first credential pattern masked the word after the
  header name, which for `Authorization: Bearer <token>` is the *scheme* —
  the token itself survived. `_AUTH_RE` now consumes an optional `bearer`
  scheme between the key and the value, and three tests pin the header form,
  the bare `Bearer <token>` form and the `key=value` form.
- **Fire-and-forget tasks.** `schedule_delivery` and `notify_kaleta_error`
  now keep the task in a module-level set with a done-callback: asyncio holds
  only a weak reference, so a delivery awaiting network I/O (or a toast) could
  be collected mid-flight.

- **Foreign keys are only enforced on postgres.** The two withdraw tests
  passed a bare `user_id=7`; SQLite does not check the FK in the test
  fixture, postgres does, and the `postgres` CI job failed on PR #116. They
  now insert real `User` rows. The postgres job's two steps were reproduced
  locally against `postgres:16` before pushing the fix.

### PII audit of existing log calls

`grep` over every `logger.*` call in `src/` for `description`, `payee`,
`account_number`, `amount`, `email` and `username` arguments found exactly
one hit: `main.py` logs the *bootstrap* API user's username
(`api`) when `KALETA_API_TOKEN` is set — an account the app creates itself,
not a person. Nothing was removed. The `RedactingFilter` masks e-mail
addresses, bearer tokens and query strings if any future call passes them.

### Manual criterion left for the owner

`[manual]` webhook → n8n → GitHub issue + e-mail (`KAL-BUG-005`).
`scripts/bug_reports.py show <id>` prints the report, its joined event
stack traces and the log excerpt as a table.

## Implementation

Landed on 2026-09-22 (PR #116).

| SHA | Author | Date | Message |
|---|---|---|---|
| `7f85aea` | Dawid Adamski | 2026-09-22 | Merge pull request #116 from DawidAdamski/plan/bug-reports-and-logging |

**Files changed:**
- .github/ISSUE_TEMPLATE/bug.yml
- alembic/env.py
- alembic/versions/l6m7n8o9p0q1_add_bug_reports.py
- docs/bdd.md
- docs/plans/bug-reports-and-logging.md
- docs/privacy-events.md
- docs/tech-stack.md
- pyproject.toml
- scripts/bug_reports.py
- src/kaleta/config/settings.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/logging_config.py
- src/kaleta/main.py
- src/kaleta/models/__init__.py
- src/kaleta/models/bug_report.py
- src/kaleta/observability/__init__.py
- src/kaleta/observability/context.py
- src/kaleta/observability/redact.py
- src/kaleta/observability/ring_buffer.py
- src/kaleta/observability/version.py
- src/kaleta/services/__init__.py
- src/kaleta/services/bug_report_delivery.py
- src/kaleta/services/bug_report_service.py
- src/kaleta/services/error_tracker.py
- src/kaleta/services/event_capture.py
- src/kaleta/services/event_retention_scheduler.py
- src/kaleta/services/event_service.py
- src/kaleta/views/bug_report_dialog.py
- src/kaleta/views/error_handling.py
- src/kaleta/views/layout.py
- src/kaleta/views/settings/page.py
- src/kaleta/views/settings/privacy_tab.py
- tests/backup_helpers.py
- tests/e2e/test_bug_report.py
- tests/integration/test_bug_report_api_context.py
- tests/unit/services/test_bug_report_service.py
- tests/unit/services/test_error_tracker.py
- tests/unit/test_logging_config.py
- uv.lock

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
