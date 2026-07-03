"""Budget overview tab — chart and summary table."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.budgets.chart import budget_chart_options
from kaleta.views.theme import BODY_MUTED, SECTION_CARD, SECTION_HEADING, TABLE_SURFACE


def render_overview_content(summaries: list[Any], *, is_dark: bool) -> None:
    if summaries:
        with ui.card().classes(SECTION_CARD):
            ui.label(t("budgets.vs_actual")).classes(f"{SECTION_HEADING} mb-4")
            chart_height = max(300, len(summaries) * 48)
            ui.echart(budget_chart_options(summaries, is_dark)).classes("w-full").style(
                f"height:{chart_height}px"
            )
    else:
        with ui.card().classes(SECTION_CARD):
            ui.label(t("budgets.no_budgets")).classes(f"{BODY_MUTED} py-4")

    if not summaries:
        return

    with ui.card().classes(SECTION_CARD):
        ui.label(t("common.description")).classes(f"{SECTION_HEADING} mb-4")
        columns = [
            {
                "name": "category",
                "label": t("common.category"),
                "field": "category",
                "align": "left",
            },
            {
                "name": "budget",
                "label": t("budgets.budgeted"),
                "field": "budget",
                "align": "right",
            },
            {
                "name": "actual",
                "label": t("budgets.actual"),
                "field": "actual",
                "align": "right",
            },
            {
                "name": "remaining",
                "label": t("budgets.remaining"),
                "field": "remaining",
                "align": "right",
            },
            {
                "name": "pct",
                "label": t("budgets.used_pct"),
                "field": "pct",
                "align": "right",
            },
        ]
        rows = [
            {
                "category": s.category_name,
                "budget": f"{s.budget_amount:,.2f} zł",
                "actual": f"{s.actual_amount:,.2f} zł",
                "remaining": f"{s.remaining:,.2f} zł",
                "pct": f"{s.percent_used:.1f}%",
            }
            for s in summaries
        ]
        table = ui.table(columns=columns, rows=rows).classes(TABLE_SURFACE).props("flat dense")
        table.add_slot(
            "body-cell-pct",
            """
            <q-td :props="props">
                <span
                    :style="{
                        color: parseFloat(props.value) > 100
                            ? '#ef5350'
                            : '#4caf50'
                    }"
                >
                    {{ props.value }}
                </span>
            </q-td>
        """,
        )
