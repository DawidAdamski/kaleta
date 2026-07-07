---
plan_id: observability-anonymous-events
title: Anonymous error events with user-driven disclosure
area: infrastructure
effort: medium
status: draft
deferred_to: q4-2026
roadmap_ref: ../roadmap.md#q4-2026-open-source-launch
---

# Anonymous error events with user-driven disclosure

Companion to [`q4-supabase-deployment`](q4-supabase-deployment.md)
(hosted instance). Settings UI surface lands via
[`ux-sidebar-workflow-and-settings`](ux-sidebar-workflow-and-settings.md) PR 2.

## Intent

When the hosted instance exists, the maintainer must be able to debug
failures **without knowing whose data it is**. Privacy model:

- Events are anonymous by design — the maintainer cannot map an event
  to a person.
- Disclosure is user-driven: an error shown to the user carries a
  short `event_id`; *they* choose to send it (plus optionally their
  session/user UUID) in a bug report, which lets the maintainer look
  up exactly that trace and fix it.

Supabase's built-in logs (Log Explorer: `postgres_logs`, `auth_logs`,
`edge_logs`; retention 1 day Free / 7 days Pro) cover only the
Supabase stack — Kaleta's Python exceptions never reach them. So the
app captures its own events into its own Postgres, which on the hosted
setup is queryable through the same Supabase dashboard. Self-hosted
instances get the identical mechanism locally — one code path.

## Scope

### 1. Event capture

- `app_events` table + model: `event_id` (short, user-displayable),
  `occurred_at`, `level`, `route`, `exception_class`, `stack_hash`,
  truncated stack (code frames only), `app_version`, `session_id` /
  `user_id` (opaque UUIDs), `request_id`.
- **Hard no-PII rule, enforced by schema**: no request bodies, no
  query params, no descriptions/amounts/payees — the event schema has
  no free-text field that could carry user data. Unit test asserts the
  payload shape.
- Middleware/exception-handler hook on the existing exception
  hierarchy (`KaletaError` + unhandled); reuses request logging from
  the Q3 hygiene work.
- Error toast/page shows `event_id` with a copy button
  ("Include this ID when reporting a bug").

### 2. Retention & access

- Cleanup job: delete events older than `KALETA_EVENT_RETENTION_DAYS`
  (default 7 — Apache-style rolling window). Runs on app startup +
  daily; no external scheduler needed.
- Maintainer lookup: SQL by `event_id` (Supabase SQL editor or psql).
  Document the query in `docs/deployment.md`.
- Config: `KALETA_EVENTS_ENABLED` (default on — data never leaves the
  instance), retention days; both surfaced in Settings → Privacy &
  diagnostics.

### 3. Docs

- `docs/` privacy note: what is captured, what never is, retention,
  how to report a bug with an event ID (also linked from the error
  toast). PRIVACY section in README for the hosted instance.

**Spec first:** add `@planned` scenarios (KAL-OBS) to `docs/bdd.md`
and a GitHub issue before implementation.

Out of scope:
- External error services (Sentry/GlitchTip) — the schema should not
  preclude a future drain, but none is wired now.
- Metrics/analytics (usage tracking) — this is error events only.
- Alerting.

## Acceptance criteria

- `grep -qE "KAL-OBS-[0-9]{3}" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `uv run pytest tests/unit -q -k "event"`
- `bash scripts/verify.sh`
- [manual] Trigger an error in the UI → toast shows a copyable
  event_id → the event is findable by SQL → contains no PII → is gone
  after the retention window.
