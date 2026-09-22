# Anonymous error events

Kaleta can record **anonymous error events** on the instance database so
maintainers can debug hosted failures without access to your financial
data.

## What is captured

Each event stores:

- Short **event ID** (shown in the UI when a server error occurs)
- Timestamp, route, exception class name
- Hash and truncated stack trace (**`src/kaleta` code frames only**)
- Application version
- Opaque session / user identifiers (numeric user id or NiceGUI client id)

## What is never captured

The schema has **no free-text field** for user data. We never store:

- Request bodies or query parameters
- Transaction descriptions, amounts, or payees
- Account names or category labels

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `KALETA_EVENTS_ENABLED` | `true` | Instance-level capture on/off |
| `KALETA_EVENT_RETENTION_DAYS` | `7` | Rolling deletion window |

Per-user opt-out: **Settings → Privacy & diagnostics → Capture anonymous
error events**.

## Bug reports

When something fails, the error tray offers **Report** — or use
**Report a problem** in the account menu, or Settings → Privacy &
diagnostics. What a report contains is listed in the dialog before you
send it:

- the summary and description **you type** (free text — write only what you
  are willing to share; it is stored unencrypted as operator data),
- an optional contact e-mail (blank by default),
- the error IDs from this session (removable, one chip each),
- the app version, the page you were on, your browser, window size and
  language,
- **only if you tick the box**: the last 200 log lines of your session,
  redacted — no amounts, payees, descriptions or account names.

Nothing is read from your ledger. Reports are kept for
`KALETA_BUG_REPORT_RETENTION_DAYS` (default 90) and then deleted. You can
withdraw any report yourself at any time: Settings → Privacy &
diagnostics → *Your reports* → delete. A self-hosted instance stores
reports in its own database; a hosted instance may forward them to the
maintainer (webhook or e-mail, see below), which is when the words you
typed leave the instance.

A report is rate-limited to 5 per session per hour.

### Where a report goes

| Variable | Default | Meaning |
|---|---|---|
| `KALETA_BUG_REPORT_WEBHOOK` | *(unset)* | `POST` the report JSON to an n8n or generic endpoint |
| `KALETA_BUG_REPORT_WEBHOOK_INCLUDE_LOGS` | `false` | Include the log excerpt in that POST |
| `KALETA_BUG_REPORT_EMAIL` + `KALETA_SMTP_*` | *(unset)* | Also e-mail the report |
| `KALETA_BUG_REPORT_RETENTION_DAYS` | `90` | Rolling deletion window |

With neither configured the report only lands in the instance database.
The maintainer reads it with:

```bash
scripts/bug_reports.py list
scripts/bug_reports.py show <report_id>
scripts/bug_reports.py close <report_id> --ref <issue url>
```

The confirmation dialog's **Open a GitHub issue** button prefills the
report ID, version, page and error IDs — never your description and never
the log excerpt.

## Structured logs

`KALETA_LOG_FORMAT=json` writes one JSON object per line carrying
`request_id`, `session_id`, `route`, `event_id` and `app_version`, so an
event ID leads to the lines around it. Every record is redacted before it
is written: bearer tokens, e-mail addresses, query strings and arguments
longer than 200 characters. Logs go to stdout only — the host ships them.

## Optional error tracker

`KALETA_ERROR_TRACKER_DSN` (extra: `tracker`) forwards the same anonymous
event to a Sentry-protocol endpoint such as a self-hosted GlitchTip. It is
**off by default**, and a `before_send` scrubber strips everything except
the exception type, the redacted frames, the route and the event ID.

## Looking up an event by hand

When you see an error toast with an **Event ID**, copy it and include it
in your GitHub issue or email. The maintainer can look up the trace with:

```sql
SELECT occurred_at, level, route, exception_class, stack_trace, app_version
FROM app_events
WHERE event_id = 'XXXXXXXX';
```

(On Supabase: SQL Editor → New query.)

## Hosted instance

See also [deployment.md](deployment.md) for Supabase Postgres setup.

## Related plan

[`docs/plans/archive/observability-anonymous-events.md`](plans/archive/observability-anonymous-events.md)
