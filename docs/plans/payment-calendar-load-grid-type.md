---
plan_id: payment-calendar-load-grid-type
title: Name the _load_grid projection type instead of Any
area: payment-calendar
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Name the _load_grid projection type instead of Any

## Intent
`payment_calendar.py::_load_grid` returns `tuple[MonthGrid, Any]`, where the
second element is the value from
`WizardProjectionService.get_payment_calendar_sources(...)`. Its real type is
`PaymentCalendarProjection`, so the `Any` erases a type the codebase already
defines and that the call site relies on (`sub_sources.subscription_charges`).
Name the type (chore inbox, `docs/plans/chores.md` ~line 219).

## Scope
- Replace the return annotation `tuple[MonthGrid, Any]` →
  `tuple[MonthGrid, PaymentCalendarProjection]` on the nested `_load_grid`
  in `src/kaleta/views/payment_calendar.py`.
- Add the import for `PaymentCalendarProjection`
  (`kaleta.schemas.wizard_projections`).

Explicitly NOT in scope:
- The `session: Any` parameter — a separate, pre-existing `Any`.
- Any runtime behaviour change. This is a typing-only fix.

## Acceptance criteria
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`

## Touchpoints
- `src/kaleta/views/payment_calendar.py`

## Open questions
None.

## Implementation notes
- No runtime behaviour change — purely a type annotation plus its import.
- No new/changed BDD scenario: Working Agreement rule 5 only applies to
  user-facing behaviour changes, and this is typing-only.
- Per Working Agreement rule 10, the type is used only in an annotation, so
  the import is placed under `if TYPE_CHECKING:` (import-linter excludes
  typing-only imports, keeping the views→services boundary clean). The sibling
  `SubscriptionCharge` is imported from the same module
  (`kaleta.schemas.wizard_projections`), so the import path matches existing
  usage.
- The actual returned type is `PaymentCalendarProjection`
  (`src/kaleta/schemas/wizard_projections.py:50`); it has the
  `subscription_charges: list[SubscriptionCharge]` attribute the call site at
  `payment_calendar.py` reads, so mypy stays green with no loosening.
