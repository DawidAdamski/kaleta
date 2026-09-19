---
plan_id: restyle-fidelity-phone-widgets
title: Restyle fidelity — the two widgets artboard 1f redraws for a phone
area: dashboard
effort: medium
status: draft
roadmap_ref: ../roadmap.md#dashboard
---

# Restyle fidelity — the two widgets `1f` redraws for a phone

## Intent

`restyle-fidelity-shell-dashboard` took the dashboard to artboards `1c`,
`1d` and `1f` and closed three rows of `1f.md` as `deviation` for one
reason, recorded there and in that plan's Implementation notes: two
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
- `wizard_actions.py` and `recent_transactions.py`: the `1f` treatments
  above, behind that flag.
- `docs/bdd.md`: `KAL-DSH-007` gains the two phone renderings; new tests
  in `tests/e2e/test_dashboard_mobile.py` with `Covers:` docstrings.
- `docs/design/restyle/fidelity/1f.md`: rows 10 and 13 move from
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
