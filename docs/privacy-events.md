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

## Reporting a bug

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

[`docs/plans/observability-anonymous-events.md`](plans/observability-anonymous-events.md)
