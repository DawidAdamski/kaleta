from __future__ import annotations

import calendar
import datetime
from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.category import CategoryType
from kaleta.schemas.budget import BudgetCreate
from kaleta.services import BudgetService, CategoryService
from kaleta.services.budget_service import CategoryRealization, RealizationStatus
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    BODY_MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
    TABLE_SURFACE,
)

# ── Range helpers ──────────────────────────────────────────────────────────────


def _range_options() -> dict[str, str]:
    return {
        "this_month": t("budgets.this_month"),
        "last_month": t("budgets.last_month"),
        "this_quarter": t("budgets.this_quarter"),
        "last_quarter": t("budgets.last_quarter"),
        "this_year": t("budgets.this_year"),
        "last_year": t("budgets.last_year"),
        "last_30_days": t("budgets.last_30_days"),
        "last_60_days": t("budgets.last_60_days"),
        "last_90_days": t("budgets.last_90_days"),
        "last_5_years": t("budgets.last_5_years"),
    }


def _date_range(key: str) -> tuple[datetime.date, datetime.date]:
    today = datetime.date.today()

    if key == "this_month":
        last_day = calendar.monthrange(today.year, today.month)[1]
        return datetime.date(today.year, today.month, 1), datetime.date(
            today.year, today.month, last_day
        )

    if key == "last_month":
        first_this = datetime.date(today.year, today.month, 1)
        end = first_this - datetime.timedelta(days=1)
        last_day = calendar.monthrange(end.year, end.month)[1]
        return datetime.date(end.year, end.month, 1), datetime.date(end.year, end.month, last_day)

    if key == "this_quarter":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        q_end_month = q_start_month + 2
        last_day = calendar.monthrange(today.year, q_end_month)[1]
        return datetime.date(today.year, q_start_month, 1), datetime.date(
            today.year, q_end_month, last_day
        )

    if key == "last_quarter":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        if q_start_month == 1:
            return datetime.date(today.year - 1, 10, 1), datetime.date(today.year - 1, 12, 31)
        prev_end_month = q_start_month - 1
        prev_start_month = prev_end_month - 2
        last_day = calendar.monthrange(today.year, prev_end_month)[1]
        return datetime.date(today.year, prev_start_month, 1), datetime.date(
            today.year, prev_end_month, last_day
        )

    if key == "this_year":
        return datetime.date(today.year, 1, 1), datetime.date(today.year, 12, 31)

    if key == "last_year":
        return datetime.date(today.year - 1, 1, 1), datetime.date(today.year - 1, 12, 31)

    if key == "last_30_days":
        return today - datetime.timedelta(days=30), today

    if key == "last_60_days":
        return today - datetime.timedelta(days=60), today

    if key == "last_90_days":
        return today - datetime.timedelta(days=90), today

    if key == "last_5_years":
        return datetime.date(today.year - 5, today.month, today.day), today

    # fallback: this month
    last_day = calendar.monthrange(today.year, today.month)[1]
    return datetime.date(today.year, today.month, 1), datetime.date(
        today.year, today.month, last_day
    )


def _range_label(key: str) -> str:
    start, end = _date_range(key)
    return f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"


# ── Chart helper ───────────────────────────────────────────────────────────────


def _budget_chart_options(summaries: list[Any], is_dark: bool = False) -> dict[str, Any]:
    categories = [s.category_name for s in summaries]
    budgeted = [float(s.budget_amount) for s in summaries]
    actual = [float(s.actual_amount) for s in summaries]
    colors_act = ["#ef5350" if s.over_budget else "#4caf50" for s in summaries]

    _opts = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": [t("budgets.budgeted"), t("budgets.actual")], "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "12%", "containLabel": True},
        "xAxis": {"type": "value", "axisLabel": {"formatter": "{value} zł"}},
        "yAxis": {"type": "category", "data": categories, "inverse": True},
        "series": [
            {
                "name": t("budgets.budgeted"),
                "type": "bar",
                "data": budgeted,
                "itemStyle": {"color": "#90caf9"},
                "barGap": "0%",
            },
            {
                "name": t("budgets.actual"),
                "type": "bar",
                "data": [
                    {"value": v, "itemStyle": {"color": c}}
                    for v, c in zip(actual, colors_act, strict=True)
                ],
            },
        ],
    }
    return apply_dark(_opts, is_dark)


# ── Realization rendering helpers ─────────────────────────────────────────────

_STATUS_COLOUR: dict[RealizationStatus, str] = {
    RealizationStatus.ON_TRACK: "positive",
    RealizationStatus.WARNING: "amber-7",
    RealizationStatus.OVER: "negative",
}

_STATUS_LABEL_KEY: dict[RealizationStatus, str] = {
    RealizationStatus.ON_TRACK: "budgets.realization.status_on_track",
    RealizationStatus.WARNING: "budgets.realization.status_warning",
    RealizationStatus.OVER: "budgets.realization.status_over",
}


def _fmt_pct(value: float) -> str:
    if value == float("inf"):
        return "∞"
    return f"{value:.0f}%"


def _render_realization_row(r: CategoryRealization) -> None:
    with ui.row().classes(
        "w-full items-center gap-3 py-2 px-3 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800"
    ):
        with ui.column().classes("flex-[2] min-w-0 gap-0"):
            ui.label(r.category_name).classes("text-sm font-medium truncate")
            if r.parent_name:
                ui.label(r.parent_name).classes("text-xs text-slate-500")
        ui.label(f"{r.planned:,.2f}").classes("flex-1 text-sm text-right tabular-nums")
        ui.label(f"{r.actual:,.2f}").classes("flex-1 text-sm text-right tabular-nums font-medium")
        remaining_cls = AMOUNT_EXPENSE if r.remaining < 0 else ""
        ui.label(f"{r.remaining:,.2f}").classes(
            f"flex-1 text-sm text-right tabular-nums {remaining_cls}"
        )
        ui.label(_fmt_pct(r.used_pct)).classes("flex-1 text-sm text-right tabular-nums")
        ui.badge(
            t(_STATUS_LABEL_KEY[r.status]),
            color=_STATUS_COLOUR[r.status],
        ).props("outline").classes("w-24 justify-center")


def _render_realization_header() -> None:
    with ui.row().classes(
        "w-full items-center gap-3 px-3 text-[11px] uppercase "
        "tracking-[0.08em] text-slate-500 font-semibold"
    ):
        ui.label(t("budgets.realization.col_category")).classes("flex-[2]")
        ui.label(t("budgets.realization.col_planned")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_actual")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_remaining")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_used_pct")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_status")).classes("w-24 text-center")


def _render_realization_flat(rows: list[CategoryRealization]) -> None:
    _render_realization_header()
    ui.separator().classes("my-1 opacity-40")
    for r in rows:
        _render_realization_row(r)


def _render_realization_grouped(rows: list[CategoryRealization]) -> None:
    groups: dict[str, list[CategoryRealization]] = {}
    for r in rows:
        key = r.parent_name or r.category_name
        groups.setdefault(key, []).append(r)

    _render_realization_header()
    ui.separator().classes("my-1 opacity-40")
    for group_name, group_rows in groups.items():
        with ui.row().classes("w-full items-center gap-2 mt-3"):
            ui.icon("folder", size="xs").classes("text-slate-400")
            ui.label(group_name).classes(
                "text-xs uppercase tracking-[0.12em] text-slate-500 font-semibold"
            )
        for r in group_rows:
            _render_realization_row(r)


# ── Page ───────────────────────────────────────────────────────────────────────


def register() -> None:
    @ui.page("/budgets")
    async def budgets_page() -> None:
        today = datetime.date.today()
        current_range: dict[str, str] = {"key": "this_month"}

        # ── Refreshable chart + table ──────────────────────────────────────
        @ui.refreshable
        async def budget_content() -> None:
            is_dark: bool = app.storage.user.get("dark_mode", False)
            start, end = _date_range(current_range["key"])
            async with AsyncSessionFactory() as session:
                summaries = await BudgetService(session).range_summary(start, end)

            if summaries:
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("budgets.vs_actual")).classes(f"{SECTION_HEADING} mb-4")
                    chart_height = max(300, len(summaries) * 48)
                    ui.echart(_budget_chart_options(summaries, is_dark)).classes("w-full").style(
                        f"height:{chart_height}px"
                    )
            else:
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("budgets.no_budgets")).classes(f"{BODY_MUTED} py-4")

            if summaries:
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
                    table = ui.table(columns=columns, rows=rows).classes(TABLE_SURFACE).props(
                        "flat dense"
                    )
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

        # ── Refreshable dialog content ─────────────────────────────────────
        @ui.refreshable
        async def dialog_content() -> None:
            async with AsyncSessionFactory() as session:
                month_summaries = await BudgetService(session).monthly_summary(
                    today.month, today.year
                )
                expense_cats = await CategoryService(session).list(type=CategoryType.EXPENSE)

            budgeted_ids = {s.category_id for s in month_summaries}
            expense_cat_opts = {c.id: c.name for c in expense_cats}
            available = {k: v for k, v in expense_cat_opts.items() if k not in budgeted_ids}

            if available:
                ui.label(t("budgets.add_category_budget")).classes("text-sm font-medium mt-2")
                new_cat_sel = ui.select(available, label=t("common.category")).classes("w-full")
                new_cat_sel.value = next(iter(available))
                new_amount = ui.number(t("budgets.amount_pln"), min=1, format="%.2f").classes(
                    "w-full"
                )

                async def save_new() -> None:
                    if not new_cat_sel.value or not new_amount.value:
                        ui.notify(t("budgets.fill_all_fields"), type="negative")
                        return
                    data = BudgetCreate(
                        category_id=new_cat_sel.value,
                        amount=Decimal(str(new_amount.value)),
                        month=today.month,
                        year=today.year,
                    )
                    async with AsyncSessionFactory() as s:
                        await BudgetService(s).upsert(data)
                    ui.notify(t("budgets.saved"), type="positive")
                    edit_dialog.close()
                    budget_content.refresh()

                ui.button(t("common.save"), on_click=save_new).props("color=primary").classes(
                    "mt-2"
                )
            else:
                ui.label(t("budgets.all_budgeted")).classes(BODY_MUTED)

            if month_summaries:
                ui.separator().classes("my-3")
                ui.label(t("budgets.edit_existing")).classes("text-sm font-medium")
                for s in month_summaries:
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.label(s.category_name).classes("flex-1 text-sm")
                        amount_field = (
                            ui.number(value=float(s.budget_amount), format="%.2f", min=0)
                            .classes("w-32")
                            .props("dense")
                        )

                        async def update_budget(
                            cat_id: int = s.category_id, field: ui.number = amount_field
                        ) -> None:
                            data = BudgetCreate(
                                category_id=cat_id,
                                amount=Decimal(str(field.value or 0)),
                                month=today.month,
                                year=today.year,
                            )
                            async with AsyncSessionFactory() as s2:
                                await BudgetService(s2).upsert(data)
                            ui.notify(t("budgets.saved"), type="positive")
                            edit_dialog.close()
                            budget_content.refresh()

                        ui.button(icon="save", on_click=update_budget).props("flat dense round")

        # ── Edit dialog (created once, outside refreshable) ────────────────
        with ui.dialog() as edit_dialog, ui.card().classes("w-96"):
            ui.label(t("budgets.edit")).classes("text-lg font-bold")
            ui.label(
                t("budgets.period_label", month=f"{today.month:02d}", year=str(today.year))
            ).classes(f"{BODY_MUTED} mb-2")
            await dialog_content()
            with ui.row().classes("w-full justify-end mt-4"):
                ui.button(t("common.close"), on_click=edit_dialog.close).props("flat")

        async def open_edit_dialog() -> None:
            dialog_content.refresh()
            edit_dialog.open()

        # ── Realization state + helpers ────────────────────────────────────
        realization_state: dict[str, Any] = {
            "year": today.year,
            "month": today.month,
            "group": "flat",
        }

        @ui.refreshable
        async def realization_content() -> None:
            year = realization_state["year"]
            month = realization_state["month"]
            group = realization_state["group"]
            async with AsyncSessionFactory() as session:
                rows = await BudgetService(session).realization_for_month(year, month)

            if not rows:
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("budgets.realization.no_rows")).classes(f"{BODY_MUTED} py-2")
                    ui.button(
                        t("budgets.realization.create_budget"),
                        icon="add",
                        on_click=open_edit_dialog,
                    ).props("color=primary unelevated").classes("mt-2")
                return

            elapsed = rows[0].elapsed_pct  # same for every row in the month
            with ui.card().classes(SECTION_CARD):
                with ui.row().classes("w-full items-center justify-between gap-3 mb-3"):
                    ui.label(t("budgets.realization.title")).classes(SECTION_HEADING)
                    ui.label(
                        t("budgets.realization.elapsed_hint", pct=f"{elapsed:.0f}")
                    ).classes(BODY_MUTED)

                if group == "by_parent":
                    _render_realization_grouped(rows)
                else:
                    _render_realization_flat(rows)

        # ── Page layout ────────────────────────────────────────────────────
        with page_layout(t("budgets.title"), wide=True):
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                ui.label(t("budgets.title")).classes(PAGE_TITLE)
                ui.button(
                    t("budgets.edit"),
                    icon="edit",
                    on_click=open_edit_dialog,
                ).props("color=primary")

            with ui.tabs().classes("w-full") as tabs:
                overview_tab = ui.tab(t("budgets.tab_overview"), icon="bar_chart")
                realization_tab = ui.tab(t("budgets.tab_realization"), icon="track_changes")

            with ui.tab_panels(tabs, value=overview_tab).classes("w-full bg-transparent"):
                with ui.tab_panel(overview_tab):
                    with ui.row().classes("w-full items-center gap-3 flex-wrap mb-2"):
                        range_date_label = ui.label(_range_label("this_month")).classes(BODY_MUTED)

                        def on_range_change(e: Any) -> None:
                            current_range["key"] = e.value
                            range_date_label.set_text(_range_label(e.value))
                            budget_content.refresh()

                        ui.select(
                            options=_range_options(),
                            value="this_month",
                            label=t("budgets.period"),
                            on_change=on_range_change,
                        ).classes("w-44")

                    await budget_content()

                with ui.tab_panel(realization_tab):
                    with ui.row().classes("w-full items-center gap-3 flex-wrap mb-2"):
                        month_opts = {
                            i: t(f"payment_calendar.month_{i}") for i in range(1, 13)
                        }
                        year_opts = {y: str(y) for y in range(today.year - 2, today.year + 3)}

                        def on_month_change(e: Any) -> None:
                            realization_state["month"] = int(e.value)
                            realization_content.refresh()

                        def on_year_change(e: Any) -> None:
                            realization_state["year"] = int(e.value)
                            realization_content.refresh()

                        def on_group_change(e: Any) -> None:
                            realization_state["group"] = e.value
                            realization_content.refresh()

                        ui.select(
                            options=month_opts,
                            value=today.month,
                            on_change=on_month_change,
                        ).classes("w-40").props("dense outlined")
                        ui.select(
                            options=year_opts,
                            value=today.year,
                            on_change=on_year_change,
                        ).classes("w-28").props("dense outlined")
                        ui.space()
                        ui.toggle(
                            {
                                "flat": t("budgets.realization.group_flat"),
                                "by_parent": t("budgets.realization.group_by_parent"),
                            },
                            value="flat",
                            on_change=on_group_change,
                        ).props("dense unelevated")

                    await realization_content()
