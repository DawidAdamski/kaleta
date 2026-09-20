---
plan_id: restyle-fidelity-phone-widgets
title: Restyle fidelity — the widgets artboard 1f redraws for a phone
area: dashboard
effort: medium
status: draft
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
- `[owner]` Opens `.fidelity/1f/index.html` and agrees that rows 10 and 13
  now read `match`.

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

_(filled in as work progresses)_
