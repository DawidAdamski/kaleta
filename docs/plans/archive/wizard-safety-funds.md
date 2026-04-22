---
plan_id: wizard-safety-funds
title: Wizard — Safety & Reserve Funds section
area: wizard
effort: medium
status: archived
archived_at: 2026-04-22
roadmap_ref: ../../product/financial-wizard.md#4-safety--reserve-funds
---

# Wizard — Safety & Reserve Funds section

## Intent

Introduce a dedicated wizard section that helps the user set up and
track dedicated reserve funds (emergency, irregular expenses,
vacation, entrepreneur buffer). Each fund has a target and a tracked
balance so the user can see coverage progress.

## Scope

- New wizard section "Safety & Reserve Funds".
- Fund types shipped as templates:
  - **Emergency** — target = 3–6× monthly expenses (user picks
    multiplier).
  - **Irregular** — target = sum of expected yearly one-offs ÷ 12 on
    a rolling horizon.
  - **Vacation** — target = user-declared yearly budget.
  - **Entrepreneur** — target = N months of business fixed costs.
- Each fund is backed by either (a) a tagged savings account, or (b)
  a virtual envelope (category-tagged balance). User picks per fund.
- Section card on the wizard shows current balance vs target with a
  progress bar and a "months of coverage" tooltip for the emergency
  fund.

Out of scope:
- Automated transfers into funds — v1 is tracking only.
- Multi-currency funds.

## Acceptance criteria

- User can create a fund from a template; target and backing mode
  are required.
- Balance updates live when the underlying account/envelope changes.
- Progress-bar logic: <50% red, 50–99% amber, ≥100% green.
- Deleting a fund never deletes transactions or accounts.

## Touchpoints

- New model `ReserveFund` (`src/kaleta/models/reserve_fund.py`)
  with fields: kind, target, backing_mode, backing_ref, created_at.
- Alembic migration.
- `src/kaleta/services/reserve_fund_service.py`.
- `src/kaleta/schemas/reserve_fund.py`.
- `src/kaleta/views/wizard.py` — new section with fund cards.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Should the emergency multiplier default to 3 or 6? v1: 3 with a
  hint that 6 is ideal.
- "Months of coverage" — denominator is trailing-90-day avg expense
  or current month's budgeted expense? v1: trailing 90-day avg, more
  stable.

## Implementation

**Shipped 2026-04-22.**

| SHA | Author | Date | Message |
|---|---|---|---|
| `TBD` | Dawid | 2026-04-22 | feat(wizard): Safety & Reserve Funds — track coverage |

**Files changed:**
- `src/kaleta/models/reserve_fund.py` (new — `ReserveFund` with `kind` and `backing_mode` str-enums)
- `src/kaleta/models/__init__.py` (exports)
- `alembic/versions/a4f9d2e7c1b8_add_reserve_funds.py` (new migration)
- `src/kaleta/schemas/reserve_fund.py` (Create/Update/Response/WithProgress; validator enforces the `backing_mode` ↔ FK invariant)
- `src/kaleta/services/reserve_fund_service.py` (CRUD + `with_progress` + `list_with_progress`; trailing-90-day expense avg for `months_of_coverage`)
- `src/kaleta/services/__init__.py` (exports)
- `src/kaleta/views/safety_funds.py` (new `/wizard/safety-funds` page — fund cards with progress bar + add-dialog with template defaults)
- `src/kaleta/views/wizard.py` (generalises the step-row link logic via `_STEP_ROUTES`; Emergency / Irregular / Vacation rows now show **Open** linking to the new page)
- `src/kaleta/views/budget_builder.py` (replaces the "Reserves step coming soon" placeholder with a live link to Safety Funds)
- `src/kaleta/main.py` (registers the new view)
- `src/kaleta/i18n/locales/en.json`, `src/kaleta/i18n/locales/pl.json` (new `safety_funds.*` block + `budget_builder.reserves_*` keys)
- `tests/unit/services/test_reserve_fund_service.py` (16 tests: schema validation, CRUD, progress pct, `months_of_coverage` with seeded transactions)

**What shipped:** `/wizard/safety-funds` route lists current funds with per-fund card (name, icon by kind, balance / target, clamped progress bar with colour by coverage: <50% negative / 50–99% amber-7 / ≥100% positive, account backing label, and for Emergency funds a "X months of expenses" footer using the trailing-90-day average expense). Add-fund dialog picks a template (Emergency / Irregular / Vacation), wires default name + optional multiplier (Emergency only), and writes via `ReserveFundService.create`. Wizard page's Safety & Reserve Funds section now has live **Open** buttons on all three steps. Budget Builder reserves card also opens the new page.

**Partial coverage (flagged for follow-up):**
- **Entrepreneur template** — listed in the plan but not in the wizard step layout; the schema's `ReserveFundKind` enum does not include it yet. Add when/if the wizard layout gains a matching step.
- **Envelope backing mode** — schema + enum plumbing is forward-compatible (`backing_mode=envelope` + `backing_category_id`) but the UI restricts the picker to account-backed funds. Envelope mode needs a category-tagged balance concept that doesn't exist yet.
- **Edit / delete UI** — service supports both, but the card currently has no inline controls. Ship when the funds list grows beyond "add-only" usage.
- **Auto-transfers, multi-currency** — already out of scope per the plan.
