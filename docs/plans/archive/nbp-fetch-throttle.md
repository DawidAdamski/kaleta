---
plan_id: nbp-fetch-throttle
title: Throttle the manual "Fetch NBP rates" button
area: settings / fx-rates
effort: small
status: archived
archived_at: 2026-10-25
roadmap_ref: ../../roadmap.md#settings
---

# Throttle the manual "Fetch NBP rates" button

## Intent
The Settings → Data "Fetch NBP rates" button hits `api.nbp.pl` on every
press, with no throttle. Any member of any family can press it, and each
press is one request for the whole instance (`public.nbp_rates`). NBP
publishes Table A once per business day, so a second manual refresh within
minutes can never add anything — yet nothing stops a user clicking it
repeatedly (e.g. on a Polish holiday, when the rates look unchanged). Give
the button a per-instance minimum interval so a refresh is allowed again
only a short while after the last successful fetch, and tell the user when.

## Scope
Covers:
- A per-instance throttle on the **manual** fetch path only. Reuses the
  existing `SendThrottle` primitive from
  `src/kaleta/auth/login_rate_limit.py` (the same one `resend_throttle`
  uses): Redis-backed when `KALETA_REDIS_URL` is set (shared across
  replicas and restarts), an in-process `MemoryStore` otherwise.
- A new module-level singleton `nbp_fetch_throttle` alongside the other
  throttle singletons, with its own store namespace (`"nbp_fetch"`).
- Two additive, side-effect-free accessors on `SendThrottle`:
  `retry_after_seconds(key)` (read, mirrors
  `LoginRateLimiter.remaining_lock_seconds`) and `mark(key)` (start the
  interval). `allow()` is left unchanged so `resend_throttle` is untouched.
- A thin check in `src/kaleta/views/settings/data_tab.py::_fetch_nbp`,
  mirroring how `views/login.py` orchestrates its limiter inline: if the
  throttle is still running, show an info toast with the minutes left and
  return without any HTTP call; otherwise fetch and, **on success only**,
  start the interval.
- New i18n key `settings.nbp_throttled` in `en.json` / `pl.json`.
- New BDD scenario **KAL-FXR-005**, `@automated`, covered by an
  integration test.

Explicitly NOT in scope:
- The daily `NbpRateScheduler` fetch — it runs once per day and must stay
  unthrottled. The throttle gates the button, not `import_latest()`.
- Any persisted last-success *date* logic or "skip when today's table is
  already stored" — that re-introduces hammering on days NBP does not
  publish (holidays), where the newest stored table is older than today.
  An attempt/last-success **interval** avoids that trap.
- No new model, table, column, or Alembic migration.

## Acceptance criteria

- `uv run pytest tests/integration/test_nbp_fetch_throttle.py -q`
- `grep -q "KAL-FXR-005" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `[manual]` Clicking "Fetch NBP rates" twice shows the wait toast on the
  second click, not a second spinner.

## Touchpoints
- `src/kaleta/auth/login_rate_limit.py` — `SendThrottle.retry_after_seconds`,
  `SendThrottle.mark`, `nbp_fetch_throttle` singleton.
- `src/kaleta/views/settings/data_tab.py` — `_fetch_nbp` throttle check.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — `settings.nbp_throttled`.
- `docs/bdd.md` — KAL-FXR-005 under "Currency rates — NBP Table A".
- `tests/integration/test_nbp_fetch_throttle.py` — covering test.

## Implementation notes
- **Lock-on-success, not on-attempt.** A failed fetch (network down) must
  stay retryable, so the interval starts only after `import_latest()`
  returns. A *successful* fetch on a holiday still starts the interval, so
  the "rates look unchanged, click again" hammer is covered regardless of
  whether rows were written.
- **Fail-open.** A throttle is best-effort, not a security lock. The
  `retry_after_seconds` read and the `mark` write are wrapped in
  `except RATE_LIMITER_BACKEND_ERRORS`: a Redis hiccup allows the fetch
  rather than blocking it (the opposite of the login path, which fails
  closed). A dropped throttle costs one extra NBP call — harmless.
- **Instance-wide key.** One fetch serves every family (into
  `public.nbp_rates`), so the throttle uses a single constant key
  (`"table_a"`), not a per-user or per-tenant key.
- **Best-effort, not atomic.** Two first presses landing at the same moment
  can both pass the `retry_after_seconds` read before either calls `mark`, so
  both fetch — the same race `LoginRateLimiter` documents. The cost is one
  extra idempotent NBP call; acceptable for a courtesy throttle.
- **Interval = 15 minutes** (KAL-FXR-005 literal). Long enough to stop
  click-spam and cover the holiday case; short enough that a legitimate
  retry after fixing a transient failure is not punished (and the daily
  scheduler covers routine updates anyway).

## Implementation

Landed on 2026-10-25 (PR #372).

| SHA | Author | Date | Message |
|---|---|---|---|
| `c51418d` | Dawid Adamski | 2026-10-24 | Merge pull request #372 from DawidAdamski/feat/nbp-fetch-throttle |

**Files changed:**
- docs/bdd.md
- docs/plans/nbp-fetch-throttle.md
- src/kaleta/auth/login_rate_limit.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/views/settings/data_tab.py
- tests/integration/test_nbp_fetch_throttle.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `uv run pytest tests/integration/test_nbp_fetch_throttle.py -q` | 0 |
| `grep -q "KAL-FXR-005" docs/bdd.md` | 0 |
| `uv run python scripts/spec_coverage.py` | 0 |
| `./scripts/verify.sh --e2e` | 0 |
