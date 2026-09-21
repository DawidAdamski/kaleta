---
plan_id: restyle-fidelity-phone-widgets
title: Restyle fidelity — the widgets artboard 1f redraws for a phone
area: dashboard
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#dashboard
---

# Restyle fidelity — the widgets `1f` redraws for a phone

## Intent

`restyle-fidelity-shell-dashboard` took the dashboard to artboards `1c`,
`1d` and `1f` and closed three rows of `1f.md` as `deviation` for one
reason, recorded there and in that plan's Implementation notes: some
widgets are drawn differently on a phone, and a widget cannot tell how
wide the page is.

- **Needs attention** (`wizard_actions`). `1c` draws the accent banner the
  app has. `1f` draws a *paper* card: the eyebrow with a mono count on one
  line, then one 44px row per item with a 6px accent dot and a
  `chevron_right`, hairlines between.
- **Latest** (`recent_transactions`). `1c` draws the five-column table the
  app has. `1f` draws 52px two-line rows — payee over "03.07 · Żywność",
  amount right in mono — because five columns do not fit 350px of content
  width.
- **The Month band** (`month_card`, and the cards beside it). `1c` gives
  each its paper card. `1f` drops the cards: In/Out/Net as bare 500/18 mono
  on the ground, a 120px chart sketch under them with month letters. At
  390px a card's 18px of padding is 10% of the width, and the band heading
  is already saying what the card's border would.
- **The safe-to-spend hero** (`safe_to_spend`). Its contents are already
  `1f`'s, measured — the eyebrow, the per-day sentence, the bar and the
  spread legend. What is left is the same card: `1f` draws the hero flat on
  the ground, and `render_safe_to_spend` builds a `DASH_CARD` it cannot opt
  out of without knowing the width. `1f.md` row 7b.

A widget's render signature is `(session: AsyncSession, is_dark: bool)`.
It is never told the width, so either treatment means changing the
signature every widget in the catalogue is registered with. That is a
registry change and new behaviour, which is why it was left out rather
than done half-way.

## Scope

- `dashboard_widgets/registry.py`: widen `RenderFn` so a widget is told
  the width it is being rendered at. Prefer one argument with a named
  meaning (`narrow: bool`, from `dashboard._viewport_is_mobile`, which
  already decides this once per page, server-side) over passing pixels —
  the decision is binary and is made in one place.
- Every `@register`ed render function updated to the new signature.
  Twenty-two of them; all but the two below ignore the new argument.
- `wizard_actions.py`, `recent_transactions.py` and the Month band's
  widgets: the `1f` treatments above, behind that flag. The Month band is
  the one that needs a decision first — whether "no card" is a property of
  the widget or of the band it is in — because it touches more than one
  render function.
- `docs/bdd.md`: `KAL-DSH-007` gains the two phone renderings; new tests
  in `tests/e2e/test_dashboard_mobile.py` with `Covers:` docstrings.
- `docs/design/restyle/fidelity/1f.md`: rows 7b, 10, 11 and 13 move from
  `deviation` to `match`, with the values read off both sides.

Out of scope: the phone tab bar (`1f.md` rows 15 and 16 — `restyle-
dashboard-mobile`'s, and left alone deliberately); the desktop grid; any
service change; the working screens.

## Acceptance criteria

- `uv run python scripts/restyle_fidelity.py check 1f`
- `uv run pytest tests/e2e/test_dashboard_mobile.py tests/e2e/test_dashboard_desktop.py -q`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` The owner opens `.fidelity/1f/index.html` and agrees that rows
  10 and 13 now read `match`, and that row 11a's two values are the right
  call.

## Touchpoints

- `src/kaleta/views/dashboard_widgets/registry.py`,
  `__init__.py`, and every module under `dashboard_widgets/`
- `src/kaleta/views/dashboard.py` (`_render_bands`, `_render_wrapped`)
- `docs/design/restyle/fidelity/1f.md`, `docs/bdd.md`, `tests/e2e/`

## Open questions

1. **One flag or a render context?** A second boolean beside `is_dark` is
   the smallest change; a small frozen dataclass (`RenderContext(is_dark,
   narrow)`) is the one that does not need doing again. Default: **the
   dataclass**, since the signature is being touched across twenty-two
   modules either way and doing it twice is the expensive option.
2. **Does the desktop keep the table?** `1c` draws it, so yes. The flag
   selects, it does not replace.

## Implementation notes

### Open question 1 — one flag or a render context? → **the dataclass**

`RenderContext(is_dark: bool, narrow: bool = False)`, frozen and slotted,
lives in `dashboard_widgets/registry.py` beside `RenderFn`. Taken as the
plan's stated default: the signature was being changed across twenty-two
modules either way, and the next thing a widget needs to know about its
surroundings should not cost that again. `narrow` defaults to `False` so a
`RenderContext(is_dark)` still reads as "the ordinary grid".

It carries a decision, not a measurement. `dashboard._viewport_is_mobile`
already makes it once per page, server-side, and every widget on that page is
drawn to the same answer; a widget told pixels would be free to disagree with
the page about which layout is being built.

### Open question 2 — does the desktop keep the table? → **yes**

`1c` draws it, so the flag selects a rendering rather than replacing one.
`test_the_desktop_dashboard_is_one_grid` now asserts both wide renderings
(the accent banner, the five-column table in its card) as well as the absence
of the phone ones, so a future `narrow` treatment cannot leak across 768px
unnoticed.

### The Month band's decision — "no card" belongs to the **widget**

Scope asked for this one to be settled first. It is a property of the widget,
and the artboard settles it: `1f` puts a paper card *in* the Month band
(Budgets, `1f.md` row 12) and draws In/Out/Net and the chart bare beside it.
A band that stripped cards from what it holds would have to put that one back,
and everything unlisted in `BAND_OF` falls into `MONTH` — balance, merchants,
trends — none of which `1f` draws at all. So `month_card` and `cashflow_chart`
each check `ctx.narrow`; `budget_variance_month` and the rest are untouched.

### What the phone Month band drops, and why that is not a loss

The wide `month_card` carries a pace bar (savings rate vs a 20% target) and a
footer of two figures (30-day balance, net worth). The phone band carries
none of the three, because the Watch band two bands down already says the
savings rate, the 30-day balance and the net worth in plain type. Saying them
twice on one screen is the thing the bands were introduced to stop.

### The chart at 120px

`_build_cashflow_chart(..., narrow=True)` drops the y-axis figures (40px of a
350px content width, repeating the In/Out figures standing above the chart),
the gridlines, and the net line — a line has to be read off a scale, and the
scale is the first thing 120px gives up. What it gains is `interval: 0` so
all six months are named (ECharts thins a crowded axis to three by itself),
a `markLine` at zero for the one rule the artboard draws, a 46% bar width off
the artboard's 26-on-56, and the current month's letter in ink via the
axis label's rich text. Two values stayed the app's rather than the
artboard's and are recorded as `1f.md` row 11a: the zero rule uses
`chart_grid_color` (`#E2DBCC`) and the bars keep the income/expense tokens
for all six months.

### "Needs attention" severity on a phone

`1f` draws both bullets in one accent tone, so the dot is a bullet and not a
severity. Severity is still carried by the ranking (`danger → warning → info`,
`KAL-WAC-004`) and `data-severity` / `data-action-kind` stay on every row, so
the ranking and routing tests read the same DOM at either width. The card has
no "Open" pill — `1f` makes each row its own target — and the `+N more` tail
above `MAX_ROWS` is a row like the others, pointing at `/wizard`, so the rest
of the list is still reachable.

### Dates disagree between the two artboards, on purpose

`1f` writes `03.07` (day, then month) and `1c` writes `07-03`. Each rendering
follows the artboard it was drawn from; `KAL-DSH-009` is scoped to a 1360px
window and is unaffected.

### `1f.md` rows

7b, 10, 11 and 13 are `match`, with the values read off both sides. Two new
sub-rows record what did not match: **11a** (the chart's zero rule and bar
tones) and **13a** (the Latest row rule is `--k-hairline` `#EDE7DA`, not the
artboard's `#E7E0D0` — the same call `3d` row 19 already records, since the
artboards use the hairline 123 times against this value's 12).

### Keyboard, and what went to the Chore inbox

The phone rows are the only route into each item (`1f` gives the card no
"Open" pill), so `_row_element` gives each one `role="button"`, `tabindex="0"`
and Enter / Space beside the click — the pattern `views/forecast.py` and the
import step indicator already use. The desktop banner's rows have the same
gap and are an unrelated file's turn: [Chore inbox
#20](https://github.com/DawidAdamski/kaleta/issues/20).

### One commit on this branch is not this plan's

`52efe6e` fixes `tests/e2e/test_transactions.py::test_a_rows_actions_are_in_
reach_without_scrolling_sideways`, which fails on `main` (verified in a
worktree) whenever the suite reaches it with the drawer expanded: it reads the
table's box mid-animation, 263.98 + 1100 > 1360. It is in its own commit per
Working Agreement §9 and is called out here because `verify.sh --e2e` cannot
go green without it.

### The sign-off criterion is spelled `[manual]`, not `[owner]`

Unchanged in substance — the owner still opens `.fidelity/1f/index.html` and
agrees rows 10 and 13 read `match` — but `[manual]` is the marker
`docs/plans/README.md` defines and the one `.claude/hooks/dod-gate.sh` and
`scripts/plan_archive.sh` skip. `[owner]` is a spelling the restyle plans
adopted between themselves; this is the first of them to run under the gate,
which tried to execute it as a shell command. The other `[owner]` plans
(`restyle-fidelity-screens`, `restyle-fidelity-shell-dashboard`,
`restyle-dashboard-rethink`, all archived) are on the Chore inbox to be
normalised.

Row 11a is named in the criterion now as well: it is a `deviation` decided
here on token-consistency grounds, so it belongs in front of the same eye
that signs off the two `match` rows.

### Not done, deliberately

`1f.md` rows 1, 2, 5a, 6, 7, 14, 15, 16 and 18 stay `deviation`: the device
frame, the shared header, the phone tab bar and the app-wide eyebrow and hero
suffix sizes are all outside this plan's Scope.
