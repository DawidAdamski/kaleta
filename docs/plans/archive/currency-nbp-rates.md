---
plan_id: currency-nbp-rates
title: Optional NBP Table A exchange-rate fetch
area: settings / currency rates
effort: medium
status: archived
archived_at: 2026-07-27
roadmap_ref: ../roadmap.md#cross-cutting-principles
source: ../plans/audit-production-readiness.md#5-currency-rates-are-manual-only--no-nbp-integration
---

# Optional NBP Table A exchange-rate fetch

## Intent

Foreign-currency accounts (e.g. Revolut EUR/USD) need up-to-date PLN
cross rates for net worth and reports. Today rates are manual-only or
derived from transfers. An optional NBP Table A fetcher (public JSON,
no API key) keeps multi-currency numbers accurate without requiring a
network for core app use.

## Scope

- NBP Table A fetcher → existing `currency_rates` via `CurrencyRateService`
- Settings Data tab: on-demand **Fetch NBP rates** button
- Opt-in **fetch on startup** (default OFF), persisted in
  `~/.kaleta/config.json`
- Fail soft when offline (toast in UI / log on startup; app continues)
- Store both directions (XXX ↔ PLN) from mid rates
- Unit tests with mocked HTTP — no live NBP calls in CI
- BDD `KAL-FXR-*` scenarios + integration coverage for `@automated` tags
  (3-letter area code required by `scripts/spec_coverage.py`; `FX` alone
  is invalid)

### Not in scope

- Paid FX APIs
- Historical backfill UI (date-range fetch from NBP)
- Auto-fetch on a schedule beyond opt-in startup
- Non-PLN base-currency cross-rate triangulation beyond stored PLN pairs

## Acceptance criteria

- `uv run pytest tests/unit/services/test_nbp_rate_service.py tests/integration/test_nbp_rates.py -q`
- `grep -E 'KAL-FXR-00[1-3]' docs/bdd.md | grep -q .`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `[manual]` With fetch-on-startup OFF, cold start does not call NBP.
- `[manual]` Offline on-demand fetch shows a negative toast; app stays usable.

## Touchpoints

- `src/kaleta/services/nbp_rate_service.py` (new)
- `src/kaleta/services/currency_rate_service.py` — batch store helper
- `src/kaleta/services/nbp_startup.py` (new) — opt-in startup hook
- `src/kaleta/config/setup_config.py` — `nbp_fetch_on_startup` flag
- `src/kaleta/exceptions.py` — typed external-service error
- `src/kaleta/api/errors.py` — 503 for external service
- `src/kaleta/main.py` — register startup fetch
- `src/kaleta/views/settings/data_tab.py` — button + toggle
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/bdd.md` — `KAL-FXR-001`…`003`
- `tests/unit/services/test_nbp_rate_service.py`
- `tests/integration/test_nbp_rates.py`

## Open questions

- None — public Table A JSON, mid rate, both directions, opt-in startup
  default OFF matches the audit fix and offline-first principle.

## Implementation notes

- Plan file was missing from the repo at pickup; created from the audit
  P1.5 brief and the agent task requirements, then set `in-progress`.
- HTTP uses stdlib `urllib.request` (no new dependency). `http_get` is
  injectable for tests; `URLError` / `OSError` / timeouts map to
  `ExternalServiceError` so injectable mocks and the default client both
  fail soft.
- Batch write via `CurrencyRateService.store_pln_mid_rates` (one commit,
  both directions) rather than per-row `create_with_inverse`.
- Fetch-on-startup lives in `~/.kaleta/config.json` (`nbp_fetch_on_startup`,
  default unset/false) so the NiceGUI/API process can read it without a
  browser session. UI checkbox on Settings → Data.
- Startup hook mirrors `BackupScheduler`: fire-and-forget task; logs and
  continues on `ExternalServiceError` / other failures.
- BDD IDs use `KAL-FXR-*` (not `KAL-FX-*`) because
  `scripts/spec_coverage.py` requires a 3–4 letter area code.

## Implementation

Landed on 2026-07-27.

| SHA | Author | Date | Message |
|---|---|---|---|
| `04be4b1` | Dawid Adamski | 2026-07-27 | feat: optional NBP Table A currency rate fetch (#30) |

**Files changed:**
- `src/kaleta/services/nbp_rate_service.py` (new), `src/kaleta/services/nbp_startup.py` (new)
- `src/kaleta/services/currency_rate_service.py`, `src/kaleta/services/__init__.py`
- `src/kaleta/config/setup_config.py`
- `src/kaleta/exceptions.py`, `src/kaleta/api/errors.py`
- `src/kaleta/main.py`
- `src/kaleta/schemas/nbp.py` (new)
- `src/kaleta/views/settings/data_tab.py`
- `src/kaleta/i18n/locales/en.json`, `src/kaleta/i18n/locales/pl.json`
- `docs/bdd.md`
- `tests/unit/services/test_nbp_rate_service.py` (new)
- `tests/integration/test_nbp_rates.py` (new)

**Acceptance criteria run** (step 3b):

| Command | Exit |
|---|---|
| `uv run pytest tests/unit/services/test_nbp_rate_service.py tests/integration/test_nbp_rates.py -q` | 0 |
| `grep -E 'KAL-FXR-00[1-3]' docs/bdd.md \| grep -q .` | 0 |
| `uv run python scripts/spec_coverage.py` | 0 |
| `./scripts/verify.sh --e2e` | 0 |
