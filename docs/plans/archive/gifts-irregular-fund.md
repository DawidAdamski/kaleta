---
plan_id: gifts-irregular-fund
title: Gifts — the yearly gift total feeds the irregular fund
area: services + views (gifts, irregular fund)
effort: small
status: archived
archived_at: 2026-10-18
roadmap_ref: ../../roadmap.md
---

# Gifts — the yearly gift total feeds the irregular fund

## Intent
Dogfooding #21 / GitHub #11, #21 — slice 2 of Gift Planning (BDD
`KAL-GFT-001`…`003`). Slice 1 built the Gifts page and the per-row `Gift`
model with a yearly total. This slice makes that yearly total show up **as a
line of the irregular-expenses fund** — the same place car insurance and
property tax live — so the money for gifts is planned and set aside the same
way: yearly amount ÷ 10 each month (`KAL-GFT-002`).

The user's domain framing (recorded as a decision below): the irregular fund
is "where we put the things we pay quarterly / half-yearly / yearly; we work
out how much we need over the year, divide by ten, and put that aside each
month", and **gifts are one of those positions**. So the Gifts line is a
genuine position of the fund, not a decorative note: it counts toward the
fund's yearly total, its monthly (÷10) total, and therefore the monthly
funding proposal.

## Scope
Slice 2 = `KAL-GFT-002` only: the yearly gifts total appears as a read-only
"Gifts" line on the irregular fund page and counts toward the fund's totals.

- **New schema `DerivedFundItem`** (`src/kaleta/schemas/irregular_item.py`): a
  fund line whose yearly amount comes from another feature rather than a stored
  `IrregularItem` row. Fields: `source: str` (e.g. `"gifts"`),
  `yearly_amount: Decimal`, and a computed `monthly_contribution` (the same ÷10
  rule as a stored item). Added to `IrregularFundPlan` as
  `derived_items: list[DerivedFundItem] = []`.
- **`IrregularItemService.plan()`** grows derived items. When the fund is the
  **primary** irregular fund (see decision below) and the yearly gifts total is
  > 0, it appends a `DerivedFundItem(source="gifts", yearly_amount=<gift total>)`.
  `yearly_total` and `monthly_total` then include the derived lines, so the
  totals row and the funding proposal (`create_funding_plan`, which reads
  `monthly_total`) both reflect gifts. Stored-item CRUD, payments and history
  are untouched; the "paid for" dropdown and history still read `plan.items`
  (real rows only — you cannot record a payment against the gifts aggregate).
- **View** (`src/kaleta/views/irregular_fund.py` `_items_card`): after the
  stored-item rows, render one read-only row per derived item — name (a link to
  the owning page), "—" due month, yearly amount, monthly ÷10 — with **no
  edit/delete buttons**. The items card and the funding card show the table /
  proposal when there are stored items **or** derived items. The totals row is
  unchanged (it already prints `plan.yearly_total` / `plan.monthly_total`).
- **i18n**: `irregular_fund.gifts_item` ("Gifts" / "Prezenty") and
  `irregular_fund.gifts_item_hint` ("From your gift list" / "Z Twojej listy
  prezentów") in `en.json` + `pl.json`.
- **Tests**: service coverage in `tests/integration/test_irregular_fund.py`
  (where the irregular-fund service tests live — the plan includes the gifts
  line and its ÷10, totals add it, non-primary funds do not get it); e2e
  `tests/e2e/test_gifts.py` extends `KAL-GFT-002` — seed a gift and an irregular
  fund, open the fund page, assert the "Gifts" line with yearly 350.00 is
  present.
- **BDD**: retag `KAL-GFT-002` `@planned` → `@automated`.

**Not in scope (binding):**
- `KAL-GFT-003` (link a transaction / mark a gift bought with actual cost) —
  later slice.
- **No per-fund pinning UI.** Choosing *which* irregular fund collects gifts
  (a flag on `ReserveFund`, migration, toggle) is a separate, larger slice.
  This slice uses the deterministic "primary fund" rule below.
- No change to stored `IrregularItem` rows, the `gifts` table, or the Gifts
  page. No new migration (the derived line is computed, never stored).
- No `api/v1` route.

## Acceptance criteria
- `uv run pytest tests/integration/test_irregular_fund.py -q`
- `uv run pytest tests/e2e/test_gifts.py -q`
- `grep -q "KAL-GFT-002 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

Fail-on-old: the new unit assertions read `plan.derived_items` and expect the
gifts line plus its contribution in the totals — neither exists on the current
`plan()`, so they fail before this slice and pass after. The e2e opens the
fund page and finds a "Gifts" line that the current page never renders.
Expected values are the BDD literals (gifts yearly total 350.00; its monthly
contribution 350.00 ÷ 10 = 35.00).

## Touchpoints
- `src/kaleta/schemas/irregular_item.py`
- `src/kaleta/services/irregular_item_service.py`
- `src/kaleta/views/irregular_fund.py`
- `src/kaleta/i18n/locales/en.json`
- `src/kaleta/i18n/locales/pl.json`
- `tests/integration/test_irregular_fund.py`
- `tests/e2e/test_gifts.py`
- `tests/e2e/seed_helpers.py`
- `docs/bdd.md`

## Open questions
- None blocking. Resolved in decisions below.

## Implementation notes
- **Decision — "primary" irregular fund.** The data model allows several
  `ReserveFund`s of kind `IRREGULAR` (no uniqueness on `kind`), but the gifts
  yearly total is one global figure not tied to any fund. Under Option A (the
  gifts line feeds the monthly funding proposal), showing it on *every*
  irregular fund would tell the user to set the gift money aside more than once.
  So the derived line is attached to exactly one fund: the **non-archived
  irregular fund with the lowest id** (`min(id)` among
  `kind == IRREGULAR, is_archived == False`). This matches the user's singular
  mental model ("the irregular fund") and the common case of exactly one. The
  natural follow-up — letting the user *choose* which fund collects gifts via a
  `ReserveFund` flag — is explicitly out of scope here (noted in chores if the
  user ever keeps two irregular funds).
- **Decision — Option A (gifts count toward the monthly amount).** Chosen by
  the user over a display-only line: the Gifts position behaves like every
  other irregular item (yearly ÷ 10 → monthly), so the on-screen monthly total
  and the funding proposal both include it. Mechanism: the derived line's
  `monthly_contribution` is summed into `plan.monthly_total`, which
  `create_funding_plan` already reads — no extra service wiring, and the
  displayed total matches what the fund proposes to transfer.
- Cross-service call: `IrregularItemService.plan()` calls `GiftService.summary()`
  (import-linter allows a service importing a service; `plan()` already composes
  with `AccountService`). `GiftService` imports no services, so no cycle.
- The derived row is read-only in the view (no `id`, not a stored row): it
  carries no edit/delete controls and is not offered as a payment target
  (`_Payments.item_options` / history keep reading `plan.items`). This avoids
  the sentinel-id hack the alternative (injecting into `plan.items`) would need,
  and keeps `IrregularItemResponse`'s `id: int` / `fund_id: int` contract intact.

## Implementation

Landed on 2026-10-18 (PR #283).

| SHA | Author | Date | Message |
|---|---|---|---|
| `0629622` | Dawid Adamski | 2026-10-18 | Merge pull request #283 from DawidAdamski/feat/gifts-irregular-fund |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/gifts-irregular-fund.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/schemas/irregular_item.py
- src/kaleta/services/irregular_item_service.py
- src/kaleta/views/irregular_fund.py
- tests/e2e/seed_helpers.py
- tests/e2e/test_gifts.py
- tests/integration/test_irregular_fund.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Still @planned in docs/bdd.md: KAL-GFT-003 — retag before or after archiving.
