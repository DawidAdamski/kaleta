# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget plan view presentation helpers."""

from __future__ import annotations

from decimal import Decimal

from kaleta.services.budget_service import PlanCategoryRow
from kaleta.views.components.amount_label import spaced_thousands
from kaleta.views.theme import ACCENT_TEXT, AMOUNT_EXPENSE, INK, MUTED


def recurring_display(row: PlanCategoryRow) -> tuple[str, str]:
    """Return label text and colour class for the recurring/monthly column.

    Accent, not ink: a figure here is the one that generated the twelve to its
    right, and artboard 2c says so by colour.
    """
    if row.uniform_monthly is not None:
        return f"{row.uniform_monthly:,.0f}", ACCENT_TEXT
    if row.has_any_plan:
        return "~", ACCENT_TEXT
    return "—", MUTED


def format_amount(amount: Decimal | None) -> str:
    return spaced_thousands(f"{amount:,.0f}") if amount else "—"


def plan_cell_color(amount: Decimal | None, is_override: bool) -> str:
    """A month that was typed over the recurring figure is the accent one."""
    if is_override:
        return ACCENT_TEXT
    if amount:
        return INK
    return MUTED


def actual_cell_color(actual: Decimal | None, is_over: bool) -> str:
    """The sub-row is quiet: only an overspent month gets a colour.

    It used to paint every month with spending green, which made a wall of
    green that said only "you spent money" — the thing a ledger always says.
    """
    return AMOUNT_EXPENSE if is_over else MUTED
