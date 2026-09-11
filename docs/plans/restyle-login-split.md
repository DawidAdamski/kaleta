---
plan_id: restyle-login-split
title: Restyle — Login as a two-panel split with a reserved error slot, phone variant (artboard 3f)
area: auth
effort: small
status: draft
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Restyle — Login two-panel split, reserved error slot, phone variant

## Intent

A single-user self-hosted app does not need a card floating in a
centred viewport. Artboard `3f` makes `auth_page_shell` a two-panel
split: the form on the sand ground at left with the wordmark above it,
and an ink panel at right carrying one line of copy and three counts
pulled from the database. The rate-limit / failed-login message gets a
**reserved slot** so it no longer pushes the button down when it
appears — the actual usability bug on the current page. The phone
version stacks the form with 48px fields and buttons.

Depends on `restyle-theme-tokens`.

## Scope

- **Shell** (`auth_common.auth_page_shell`): two panels ≥ `md`: left
  (ground) wordmark + title + subtitle + form; right (ink `--k-ink`,
  text `--k-surface`) one line of copy and three counts. Under `md` the
  right panel is hidden and the form fills the viewport with 48px
  controls. The shell keeps its signature (title/subtitle keys) so
  `login.py` and any other auth page (setup, reset) keep working.
- **Counts**: transactions, accounts, months of history — read via a
  small `AuthLandingStats` service method (read-only, cached per
  process for 60 s). If the DB is empty / not set up, show the copy
  without counts. Never expose amounts.
- **Reserved error slot**: a fixed-height (`min-h-[20px]`) line between
  the password field and the button; `error.set_text` writes into it.
  Rate-limit and failed-login messages unchanged.
- Phone: fields and button `min-h-[48px]`; no Face ID button (the mock
  shows one — it is a proposal, out of scope).
- BDD: `KAL-AUTH-011` "failed-login message does not move the submit
  button" (@automated, e2e: button bounding box y unchanged after a
  failed attempt).

Out of scope: any auth logic, rate limiter, password reset flow,
biometric login.

## Acceptance criteria

- `uv run pytest tests/e2e/test_auth.py -q`
- `uv run pytest tests/unit/auth -q`
- `grep -q "KAL-AUTH-011" docs/bdd.md`
- `grep -q "min-h-" src/kaleta/views/login.py`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` 1360px: split layout matches artboard `3f`; 390px: stacked
  form with 48px controls; wrong password: message appears in place,
  button does not move.

## Touchpoints

- `src/kaleta/views/auth_common.py`, `login.py`
- `src/kaleta/services/` (stats helper — smallest home that fits,
  e.g. `stats_service` if one exists)
- `src/kaleta/i18n/locales/en.json`, `pl.json` (`auth.panel_copy`,
  `auth.panel_count_*`)
- `docs/bdd.md`, `tests/e2e/test_auth.py`

## Open questions

1. Show counts before login at all (information disclosure)? Default:
   **yes, counts only** — a single-user self-hosted app; make it a
   settings-free constant `AUTH_PANEL_STATS = True` so it can be turned
   off in one line if the public demo instance should not show them.

## Implementation notes

_Filled in as work progresses._
