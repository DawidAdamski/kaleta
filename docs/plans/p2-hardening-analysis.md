---
plan_id: p2-hardening-analysis
title: P2 — hardening & analysis ergonomics (LAN / headless)
area: cross-cutting
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# P2 — hardening & analysis ergonomics

Converts findings 11–16 from [`audit-production-readiness.md`](audit-production-readiness.md).
One branch ships all four work packages (umbrella); split further only if review demands it.

See Cursor plan / agent notes for sequential WP detail. Scope summary:

1. **WP1** — `KALETA_API_TOKEN` API-mode user bootstrap + tests; default DB under `~/.kaleta`; docs/audit honesty (#13, #16).
2. **WP2** — login rate-limit + session TTL; cookie auth read-only for API (#11, #12).
3. **WP3** — full ledger CSV export next to backup (#15).
4. **WP4** — read-only API for subscriptions, loans, reserve funds, net worth, cashflow, income-statement (#14).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_api_token_service.py tests/unit/services/test_auth_service.py -q`
- `uv run pytest tests/unit/auth tests/integration -q -k 'env_token or rate_limit or session_ttl or bearer or ledger_csv or subscriptions or net_worth or cashflow or income_statement' || true`
- `./scripts/verify.sh` (with `--e2e` after view changes)
- `[manual]` Audit P2 section links here and notes finding 13 correction

## Not in scope

- Parquet export; full canned-report API parity; CSRF tokens (bearer-for-mutations instead); git history scrub.
