---
plan_id: restyle-fidelity-screens
title: Restyle fidelity — the ten working screens to artboards 2a–2d and 3a–3f
area: ux
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#ux
---

# Restyle fidelity — working screens

## Intent

The behaviour the restyle plans built is right — filter chips that show
their value, pace bars with a month tick, forecast on load, the overdue
strip, the login error slot. What is off is the picture: each screen was
built from a paragraph of README prose and never compared with its artboard.
This plan is the comparison, screen by screen, and the fixes it turns up.

Depends on `restyle-fidelity-shell-dashboard`: every artboard here is drawn
inside the paper header and the 64px mini drawer, and until that shell is
back no screen can match.

## Method

The loop in `restyle-fidelity-shell-dashboard` § Method, unchanged: read
`artboards/<id>.html` whole → `shoot <id>` → look at both pictures → write
the report with observed values → transcribe structure and values for every
`open` row → shoot again → `check <id>`.

One artboard at a time, **one commit per artboard**, in this order (highest
traffic first): `2a`, `2b`, `3c`, `3b`, `3a`, `2c`, `2d`, `3d`, `3e`, `3f`.

## Scope

| Artboard | Screen | Route | Views |
|---|---|---|---|
| `2a` | Transactions | `/transactions` | `views/transactions/`, `views/components/` |
| `2b` | Budgets → Realization | `/budgets` (Realization tab) | `views/budgets/` |
| `2c` | Budget Plan | `/budget-plan` | `views/budget_plan/` |
| `2d` | Import, step 3 | `/import` (after upload) | `views/import_view/` |
| `3a` | Forecast | `/forecast` | `views/forecast.py`, `views/chart_utils.py` |
| `3b` | Net Worth | `/net-worth` | `views/net_worth.py` |
| `3c` | Payment Calendar | `/payment-calendar` | `views/payment_calendar.py` |
| `3d` | Financial Wizard | `/wizard` | `views/wizard.py` |
| `3e` | Report builder | `/reports/builder` | `views/reports/` |
| `3f` | Login, desktop + phone | `/login` | `views/login.py`, `views/auth_common.py` |

- View layer only: layout, classes, tokens, element order. A value that
  recurs across screens becomes a token in `theme.py`.
- Charts: ECharts options (colours, axis and legend treatment, annotations)
  are in scope; the artboards' SVG shapes are sketches and are not.
- If the seed cannot put a screen in the state its artboard draws (no overdue
  occurrence for `3c`, no over-budget row for `2b`), extend the script's
  `_prepare_*` hook or the seed — do not mark the element `deviation` for
  want of data.
- Existing `KAL-` scenarios keep passing unchanged. A selector that moves is
  updated in the test; an assertion is not loosened (Working Agreement §4).

Out of scope: new behaviour, service changes, the phone pass for screens
other than `3f`, artboards `1a` / `1b` / `1e`. If a screen's `open` rows turn
out to need a service change, stop on that screen, leave the row `open`, and
say so — it becomes its own plan.

If one screen alone is more than a day's work, split it out into
`restyle-fidelity-<screen>` and drop its criterion from this plan.

## Acceptance criteria

- `uv run python scripts/restyle_fidelity.py check 2a`
- `uv run python scripts/restyle_fidelity.py check 2b`
- `uv run python scripts/restyle_fidelity.py check 2c`
- `uv run python scripts/restyle_fidelity.py check 2d`
- `uv run python scripts/restyle_fidelity.py check 3a`
- `uv run python scripts/restyle_fidelity.py check 3b`
- `uv run python scripts/restyle_fidelity.py check 3c`
- `uv run python scripts/restyle_fidelity.py check 3d`
- `uv run python scripts/restyle_fidelity.py check 3e`
- `uv run python scripts/restyle_fidelity.py check 3f`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[owner]` Pages through `.fidelity/<id>/index.html` for the ten artboards
  and agrees with every row marked `deviation`.

## Touchpoints

- The view modules in the Scope table; `src/kaleta/views/theme.py`
- `docs/design/restyle/fidelity/<id>.md` × 10
- `scripts/restyle_fidelity.py` (`_prepare_*` hooks only), `scripts/seed.py`
  if a state is missing
- `tests/e2e/` where a selector moves

## Open questions

1. **Dark mode.** Only the dashboard has a dark artboard (`1d`). Default:
   the working screens are compared in light only; dark is covered by the
   tokens `1d` validates. If a screen hard-codes a light hex, that is an
   `open` row on that screen.

## Implementation notes

_(filled in as work progresses)_
