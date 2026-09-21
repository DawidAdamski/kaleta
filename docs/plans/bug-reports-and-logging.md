---
plan_id: bug-reports-and-logging
title: Bug reports from the app, and structured logs to read them by
area: observability / settings
effort: medium
status: draft
roadmap_ref: ../roadmap.md#cross-cutting-principles
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
([observability-anonymous-events](archive/observability-anonymous-events.md))
and respects the encryption promise of
[ADR-35](../adr/035-hosted-multi-tenancy-and-user-held-encryption.md):
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

(filled in as work progresses)
