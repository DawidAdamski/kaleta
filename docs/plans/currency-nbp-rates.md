---
plan_id: currency-nbp-rates
title: Currency — optional NBP Table A rate fetch
area: currency / settings
effort: medium
status: draft
roadmap_ref: ../roadmap.md#cross-cutting-principles
source: audit-production-readiness.md#5-currency-rates-are-manual-only--no-nbp-integration
---

# Currency — optional NBP Table A rate fetch

## Intent

Foreign-currency accounts (e.g. Revolut EUR/USD) make net worth and
reports drift between manual FX updates. Add an **optional**,
**offline-safe** fetcher for Narodowy Bank Polski Table A (public JSON,
no API key) that upserts into the existing `currency_rates` table —
on demand from Settings, and optionally on app start.

## Scope

- New `NbpRateFetcher` (or equivalent) service that:
  - GETs the latest NBP Table A JSON (`api.nbp.pl/.../tables/A/?format=json`)
  - Maps mid rates into PLN↔foreign pairs (and inverse) for currencies
    already used by accounts / assets (or all table-A codes — prefer
    pairs relevant to the ledger via existing
    `CurrencyRateService.build_relevant_pairs` if present)
  - Persists via `CurrencyRateService.create` / bulk upsert into
    `currency_rates` with the NBP effective date
- Settings → Data (or General): **"Fetch NBP rates"** button +
  opt-in **"Fetch rates on startup"** toggle (default **off**)
- On-start hook in `main` lifespan / preload: if toggle on, attempt
  fetch; on network / HTTP failure log + soft and continue — app
  must work with no network
- Unit tests with mocked HTTP responses (fixture JSON); **no live
  NBP calls in CI**
- BDD scenarios for on-demand success and offline soft-fail
  (`KAL-FX-001+` or under Settings)

### Not in scope

- Paid / third-party FX APIs
- Historical backfill UI beyond "latest Table A"
- Changing how transfer-derived rates are recorded
- Background cron outside the Kaleta process

## Acceptance criteria

- `uv run pytest tests/unit/services/test_nbp_rate_fetcher.py tests/unit/services/test_currency_rate_service.py -q`
- `grep -E 'KAL-FX-|NBP' docs/bdd.md | grep -q .`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh`
- `[manual]` With network blocked, enabling fetch-on-start does not
  prevent the app from serving pages; a negative toast or log line
  records the failure.

## Touchpoints

- `src/kaleta/services/nbp_rate_fetcher.py` (new) or similar
- `src/kaleta/services/currency_rate_service.py`
- `src/kaleta/config/settings.py` — optional env for enable-on-start
  if not only UI storage
- `src/kaleta/views/settings/` — Data/General tab button + toggle
- `src/kaleta/main.py` — optional startup trigger
- `src/kaleta/i18n/locales/{en,pl}.json`
- `tests/unit/services/test_nbp_rate_fetcher.py`
- `docs/bdd.md` — new FX / Settings scenarios

## Open questions

1. Persist fetch-on-start in NiceGUI user storage vs
   `KALETA_NBP_FETCH_ON_START` env — default: **user storage** to
   match other Features toggles; env override optional later.
2. Store rates as `from=XXX,to=PLN` only, or always store both
   directions (mirror `record_transfer_rate`)? Default: **both**.

## Implementation notes

_Filled in as work progresses._

Source finding: `audit-production-readiness` P1.5. One plan = one
branch = one PR.
