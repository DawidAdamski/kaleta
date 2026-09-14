# SPDX-License-Identifier: AGPL-3.0-or-later
"""Colour rules for the annual plan grid's cells (artboard 2c).

Covers: KAL-BUD-006 — "a month that went over its budget is highlighted, and
a month that stayed inside it is not". The e2e proves both halves render;
these pin the rule itself, including the cases a browser test never seeds.
"""

from __future__ import annotations

from decimal import Decimal

from kaleta.services.budget_service import PlanCategoryRow, PlanMonthCell
from kaleta.views.budget_plan.helpers import (
    actual_cell_color,
    format_amount,
    plan_cell_color,
    recurring_display,
)
from kaleta.views.theme import ACCENT_TEXT, AMOUNT_EXPENSE, INK, MUTED


def _row(**kwargs: object) -> PlanCategoryRow:
    defaults: dict[str, object] = {
        "category_id": 1,
        "name": "Żywność",
        "parent_id": None,
        "is_child": False,
        "uniform_monthly": None,
        "has_any_plan": False,
        "has_any_actual": False,
        "months": tuple(
            PlanMonthCell(
                month=m, planned=None, actual=None, is_override=False, is_over_budget=False
            )
            for m in range(1, 13)
        ),
        "total_planned": Decimal("0"),
        "total_actual": Decimal("0"),
    }
    defaults.update(kwargs)
    return PlanCategoryRow(**defaults)  # type: ignore[arg-type]


class TestActualCellColour:
    def test_an_overspent_month_is_the_expense_colour(self) -> None:
        assert actual_cell_color(Decimal("260.00"), True) == AMOUNT_EXPENSE

    def test_a_month_inside_its_budget_stays_quiet(self) -> None:
        # It used to come back green. Twelve green months say only "you spent
        # money", which is what a ledger always says.
        assert actual_cell_color(Decimal("450.00"), False) == MUTED

    def test_a_month_with_no_spending_stays_quiet(self) -> None:
        assert actual_cell_color(None, False) == MUTED


class TestPlanCellColour:
    def test_a_month_typed_over_the_recurring_figure_is_accent(self) -> None:
        assert plan_cell_color(Decimal("900.00"), True) == ACCENT_TEXT

    def test_a_planned_month_is_ink(self) -> None:
        assert plan_cell_color(Decimal("800.00"), False) == INK

    def test_an_empty_month_is_muted(self) -> None:
        assert plan_cell_color(None, False) == MUTED


class TestRecurringColumn:
    def test_a_uniform_year_shows_the_monthly_figure_in_accent(self) -> None:
        assert recurring_display(_row(uniform_monthly=Decimal("800"))) == ("800", ACCENT_TEXT)

    def test_an_uneven_year_shows_a_tilde(self) -> None:
        assert recurring_display(_row(has_any_plan=True)) == ("~", ACCENT_TEXT)

    def test_an_unplanned_category_shows_an_em_dash(self) -> None:
        assert recurring_display(_row()) == ("—", MUTED)


class TestFormatAmount:
    def test_an_empty_month_is_an_em_dash_not_a_zero(self) -> None:
        assert format_amount(None) == "—"
        assert format_amount(Decimal("0")) == "—"

    def test_a_figure_keeps_its_separator_and_drops_its_cents(self) -> None:
        assert format_amount(Decimal("1234.56")) == "1,235"
