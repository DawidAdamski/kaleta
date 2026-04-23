---
plan_id: safety-funds-months-bar
title: Safety funds — months-as-ticks progress bar
area: wizard
effort: small
status: draft
roadmap_ref: ../product/financial-wizard.md#4-safety--reserve-funds
---

# Safety funds — months-as-ticks progress bar

## Intent

On an emergency fund, the user sets two numbers today — a PLN target
and a "Cover: N months" multiplier — but the progress bar only reacts
to the PLN target, and the "months of expenses" line reacts to
trailing spending. These two metrics disagree whenever the user's
target isn't mathematically sized for their trailing spending, which
is often.

Reframe the multiplier as the user's own declaration of
"one month's survival money = target ÷ N". The progress bar then
shows N equal chunks via tick marks, and the footer line becomes
`You will survive for X months` where `X = balance ÷ (target ÷ N)`.
No reliance on trailing spending; one target, one user-defined
chunk size, one consistent story.

Concrete example the user gave: target 100,000 zł, multiplier 10 →
bar has a tick every 10,000 zł, and the footer reads "You will
survive for X months" based on balance.

## Scope

- Split the emergency fund progress bar into `multiplier` equal
  chunks with visible tick marks.
- Footer for emergency funds becomes `You will survive for X months`
  (X = `balance ÷ (target ÷ multiplier)`, 1 decimal).
- Drop the trailing-90-day expense calculation from the progress
  display (keep `_trailing_monthly_expense` in the service only if
  something else uses it; otherwise remove).
- Only emergency funds get tick marks + survival text; irregular /
  vacation funds render unchanged.
- Edge cases:
  - `target == 0` → no ticks, no survival text, neutral bar.
  - `multiplier in (None, 0, 1)` → no ticks (single chunk is a plain
    bar).
  - `balance > target` → bar caps at 100% with a subtle "surplus"
    marker; survival text may exceed `multiplier` (e.g. `12.0 / 10`).

Out of scope:
- Auto-syncing target and multiplier (user's explicit choice —
  they want to keep both as free inputs, not derived).
- Separate "essential expenses" category flag to feed back into the
  UI. Covered elsewhere if ever needed.
- Tick marks on irregular / vacation funds (different mental model).

## Acceptance criteria

- Given an emergency fund with `target=100000`, `multiplier=10`,
  `balance=35000`:
  - Bar is 35% filled.
  - Bar shows 9 vertical tick marks at 10%, 20%, …, 90%.
  - Footer reads `You will survive for 3.5 months` (en) /
    `Wystarczy na 3,5 miesiąca` (pl).
- Given `multiplier=None` (legacy row) the bar has no ticks and the
  footer falls back to the current `months_of_coverage` line — or, if
  the trailing calc is removed, hides the footer line entirely.
- Given `balance > target`, the bar is full and the survival text
  shows `12.0 / 10 months` (or equivalent wording) without overflow.
- Tick-mark rendering works in both light and dark themes.

## Touchpoints

- `src/kaleta/views/safety_funds.py`:
  - `_render_fund_card` — wrap the `ui.linear_progress` in a relative
    container with absolutely-positioned tick-mark divs at
    `(i / multiplier) × 100%` for `i in 1..multiplier-1`.
  - Replace the `months_of_coverage` label with a survival label for
    emergency funds.
- `src/kaleta/services/reserve_fund_service.py` — decide whether to
  keep `_trailing_monthly_expense` and the `months_of_coverage` field
  on `ReserveFundWithProgress`. Likely keep the field but rename it
  or add `survival_months` alongside.
- `src/kaleta/schemas/reserve_fund.py` — same: add
  `survival_months: Decimal | None` to `ReserveFundWithProgress` if
  we compute it server-side. Alternatively the view can derive it
  (pure function of balance/target/multiplier, no service needed).
- `src/kaleta/i18n/locales/{en,pl}.json` — add
  `safety_funds.survival_months` and deprecate or keep the old
  `months_of_coverage*` keys depending on #1 in Open questions.
- `tests/unit/services/test_reserve_fund_service.py` — if server
  computes survival months, add tests; otherwise nothing to add.

## Open questions

1. Keep the trailing-spending `months_of_coverage` as a secondary
   muted line ("At your avg spending, this covers ~0.8 months")?
   Or drop it entirely and let the user-defined chunk be the only
   months metric? Default: **drop** — the whole point of this plan is
   to remove the contradiction.
2. Compute survival months server-side (new field on
   `ReserveFundWithProgress`) or in the view? Default: **view-side**,
   since it's a trivial pure calculation and keeps the service
   surface small.
3. Visual weight of ticks — 1 px full-height, or short 3 px stubs
   above/below the bar? Default: thin full-height white-20% lines,
   matching the existing dark-theme palette.
4. Tick styling when a tick falls below the current fill
   (i.e. "month survived") vs above it — same colour, or a stronger
   tick for reached milestones? Default: same colour; don't
   over-design the milestone story yet.

## Implementation notes
_Filled in as work progresses._
