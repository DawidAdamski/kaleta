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
- Existing `KAL-` scenarios keep passing. A selector that moves is updated in
  the test; an assertion is not loosened (Working Agreement §4). Where an
  artboard renames the thing a scenario quotes — a step title, a heading, the
  place a strip sits — the scenario is re-worded with it (Working Agreement
  §5) and the re-wording is listed in `## Implementation notes`. What a
  scenario claims does not change; only the words it quotes from the screen.

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

### Open questions, resolved

1. **Dark mode.** Default taken: the ten screens were compared in light
   only. Every value this plan introduced is a CSS custom property on
   `:root` with a `.body--dark` counterpart (`--k-band`, `--k-ramp-1..6`,
   `--k-warm-ink`, `--k-warm-rule`, `--k-field-border`), so no screen
   hard-codes a light hex and no row is open for want of a dark pass.

### Decisions

- **The shoot runs the rich seed.** `EphemeralApp` was seeding through
  `DataService.seed`, which has no payees, tags, planned transactions,
  subscriptions or physical assets — so `2a`, `3b` and `3c` were being
  photographed against a ledger their artboards do not describe. It now
  runs `alembic upgrade head` → `scripts/seed.py` → `alembic stamp head`
  → `reset_demo.py --force --no-seed`, which is why `reset_demo` gained
  a `--no-seed` flag.
- **`3f` was photographing the dashboard.** The Shooter logged in once
  per theme, and a logged-in session redirects `/login`. Artboards with
  `needs_login=False` are shot in a fresh context of their own.
- **Quasar's colour helpers cannot be out-specified.** `.bg-primary` and
  `.text-white` are `!important`. Every ink-on-chosen control in this
  branch — the segmented controls, the ledger checkbox, the chart-type
  squares — works by redefining `--q-primary` / `--q-info` scoped to the
  component and passing `toggle-text-color=info` or `color="info"`.
- **Quasar fixes table row heights.** `.q-table thead tr` and
  `.q-table tbody td` are 48px; `2a`'s 39px header and 35px rows need
  `height:auto` on both, plus an 18px checkbox inner.
- **`views_hash` covers `theme.py`.** Any token change invalidates every
  report, so all ten were written after the last source change and
  `shoot all` was run once more before `check`.
- **The artboards draw three card paddings, so the app has three.**
  20px (`SECTION_CARD`) where a card holds a grid or a chart that wants
  the room; `22px 24px` (`SECTION_CARD_WIDE`) on `2d`'s two mapping
  cards, `3a`'s two foot cards, `3b`'s physical assets, `3c`'s day sheet
  and `3e`'s sentence; `24px 26px` (`SECTION_CARD_FEATURE`) on the one
  card a screen is about — `3a`'s chart, `3b`'s chart, `3d`'s mentor
  note, `3e`'s result. Five reports had called `22px 24px` a match for
  `SECTION_CARD`'s 20px and four had done the same for `24px 26px`; they
  now match because the padding does, not because the row says so.
- **Two warm sands, because the artboards draw two.** `2a` tints the
  selection bar `#EFE3D6` (`--k-surface-warm-strong`); `2d`'s
  unparseable-rows note and `3c`'s Overdue card and strip are a step
  lighter at `#F4E9DC`, which is now `--k-surface-notice`. The first
  pass called the difference a fourth sand nothing wanted, which was
  wrong: three elements across two artboards want it.
- **The thousands separator is a space, through one function.** The
  restyled screens were each doing `.replace(",", " ")` at the point of
  use, which left `2c` writing `2,400` beside `3c` writing `2 400`.
  `spaced_thousands` in `views/components/amount_label.py` is the one
  place that knows, and `budget_plan.helpers.format_amount` — the only
  other writer of a grouped figure on these ten screens — goes through
  it too. Screens outside this plan still write Python's comma; that is
  the next plan's to finish, not this one's to leave half-done on a
  screen it did restyle.
- **The strip's button posts through the service, not in the view.**
  `_post_overdue` looped over `post_occurrence` with a session each, so
  the orchestration — and the atomicity — lived in `views/`.
  `PlannedTransactionService.post_occurrences` takes the list and
  commits once; the view calls it once and counts what came back. Three
  unit tests cover it.
- **The seed's canonical tags carry sand colours.** A tag chip is drawn
  as an outline in its own colour, and the model's grey default read as
  "no tag" beside a category pill in `2a`'s shot.

### What the comparison fixed rather than recorded

- A net-worth liability row drew its debt as a credit: the account
  already holds a negative balance and the view negated it. `-abs`.
- The import mapping's AUTO mark was a green outlined pill sitting on
  the field's own border (`align-self:flex-start` in Quasar's append
  slot). Artboard `2d` writes it as quiet type inside the box.
- Both forecast tables gave each row its own column widths: a bare `fr`
  track takes its minimum from its content, so one long category name
  moved every figure in the card. `minmax(0, …)`.
- The report builder's rail highlight shrink-wrapped its own label; the
  rail row is `width:100%`.

### Behaviour that changed, and where it is written down

- The Payment Calendar's day sheet is a panel beside the grid, open on
  today, rather than a drawer over it — `KAL-PLN-026`, covered by
  `test_the_day_sheet_sits_beside_the_month`.
- Its overdue strip reads as one line and carries one button that posts
  exactly the items it names (`_post_overdue`, not `post_due`, so the
  count on the button is the count it posts) — `KAL-PLN-020`, rewritten
  and its test with it.
- The report builder's bar result is rows of HTML rather than an ECharts
  canvas — `KAL-RPT-002`, covered by `test_the_bar_result_reads_as_rows`.
  `_bar_options` went with it.
- The forecast horizon is three buttons rather than a menu, and the date
  a figure is as of moved from a third line on the card to `data-as-of`
  plus a tooltip. Three `KAL-FCT` e2e selectors moved with the controls;
  none of their assertions was loosened.
- The seed grows two already-late planned transactions: the overdue
  strip and the Overdue card exist for that state, and a seed in which
  nothing is ever late leaves both untested and unseen.
- Four artboards renamed what they show, so four `KAL-` scenarios that
  quoted the old words were re-worded with them and no others:
  `KAL-ONB-001` / `KAL-ONB-002` (the setup steps are Institutions,
  Accounts, Categories and First import) and `KAL-CSV-026` (the
  parse-failure strip is under the sample rows it numbers, because `2d`
  puts the sample and the pickers in two cards side by side, and
  "above the pickers" stopped being a place).
- The rest of the suite moved with the markup rather than with the
  words: a realization row is a `.k-realization-body` grid cell, a
  mapping picker is found through the `.k-field-row` it shares with its
  label, and a setup card through `data-setup-step`. Every assertion
  that moved kept its strength — the login panel still has to add up to
  three labels, three integers and one sentence with nothing left over.

### Deviations the owner has to agree with

Every `deviation` row in the ten reports says why. The ones that are a
missing capability rather than a design choice:

- `2a` has no Export button — the app has no ledger export.
- `3e` has no Export CSV, and its eyebrow counts the whole ledger rather
  than the rows in scope (that count needs the service to answer).
- `3f`'s error says "Invalid username or password" without the artboard's
  "3 attempts left" (`LoginRateLimiter` keeps the count but nothing
  exposes it), and its third panel stat is months of history, not banks.
- `3c`'s day sheet has no "Post this day"; each item carries the button
  that posts it.
- `2d` maps Counterparty, Debit and Credit as three rows where the
  artboard draws one "Debit / Credit" picker.

All five are new behaviour or service changes, which this plan's Scope
puts out of bounds.

One more needs the owner's nod for the opposite reason — it is a change
the artboard asked for rather than one it was refused:

- `3e`'s bar result is rows of HTML, not an ECharts canvas. Scope puts
  "ECharts options" in bounds and the artboards' SVG sketches out of
  them, and this sits between the two: artboard `3e` draws the bar
  result as a labelled rule per row with the figure and the share beside
  it, which is a list and not a chart, and no option on an ECharts bar
  produces it. `_bar_options` went with the canvas; `KAL-RPT-002` and
  `test_the_bar_result_reads_as_rows` cover what replaced it, and
  `report_chart_options` still answers for the three types that really
  are charts.
