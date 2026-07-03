"""Budget plan view presentation helpers."""

from __future__ import annotations

from decimal import Decimal

from kaleta.services.budget_service import PlanCategoryRow


def recurring_display(row: PlanCategoryRow) -> tuple[str, str]:
    """Return label text and colour class for the recurring/monthly column."""
    if row.uniform_monthly is not None:
        return f"{row.uniform_monthly:,.0f}", "text-primary"
    if row.has_any_plan:
        return "~", "text-orange-8"
    return "—", "text-grey-4"


def format_amount(amount: Decimal | None) -> str:
    return f"{amount:,.0f}" if amount else "—"


def plan_cell_color(amount: Decimal | None, is_override: bool) -> str:
    if is_override:
        return "text-orange-8"
    if amount:
        return "text-primary"
    return "text-grey-4"


def actual_cell_color(actual: Decimal | None, is_over: bool) -> str:
    if is_over:
        return "text-red-6"
    if actual:
        return "text-green-6"
    return "text-grey-4"
