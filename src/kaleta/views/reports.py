from __future__ import annotations

import json
from typing import Any

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.category import CategoryType
from kaleta.schemas.report import SavedReportCreate
from kaleta.services import AccountService, CategoryService
from kaleta.services.saved_report_service import (
    ReportConfig,
    ReportResult,
    SavedReportService,
    build_echart_option,
)
from kaleta.views.layout import page_layout

# ── Field definitions ──────────────────────────────────────────────────────────

_DIMENSIONS = [
    ("category", "reports.dim_category", "category"),
    ("account", "reports.dim_account", "account_balance_wallet"),
    ("month", "reports.dim_month", "calendar_month"),
    ("year", "reports.dim_year", "calendar_today"),
    ("type", "reports.dim_type", "swap_horiz"),
    ("institution", "reports.dim_institution", "account_balance"),
    ("weekday", "reports.dim_weekday", "today"),
]

_METRICS = [
    ("sum", "reports.metric_sum", "functions"),
    ("count", "reports.metric_count", "tag"),
    ("avg", "reports.metric_avg", "percent"),
]

_CHART_TYPES = [
    ("bar", "bar_chart"),
    ("line", "show_chart"),
    ("pie", "pie_chart"),
    ("donut", "donut_large"),
    ("table", "table_chart"),
]

_DATE_PRESETS = [
    ("all_time", "reports.preset_all"),
    ("this_month", "reports.preset_this_month"),
    ("last_month", "reports.preset_last_month"),
    ("this_year", "reports.preset_this_year"),
    ("last_year", "reports.preset_last_year"),
    ("last_30", "reports.preset_last_30"),
    ("last_90", "reports.preset_last_90"),
    ("last_12_months", "reports.preset_last_12"),
    ("custom", "reports.preset_custom"),
]

_TX_TYPES = [
    ("expense", "reports.type_expense", "trending_down", "negative"),
    ("income", "reports.type_income", "trending_up", "positive"),
    ("transfer", "reports.type_transfer", "swap_horiz", "primary"),
]


def _chart_icon(chart_type: str) -> str:
    icons = {
        "bar": "bar_chart",
        "line": "show_chart",
        "pie": "pie_chart",
        "donut": "donut_large",
        "table": "table_chart",
    }
    return icons.get(chart_type, "bar_chart")


def register() -> None:
    @ui.page("/reports")
    async def reports_page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)

        async with AsyncSessionFactory() as session:
            accounts = await AccountService(session).list()
            all_categories = await CategoryService(session).list(type=CategoryType.EXPENSE)

        account_options = {a.id: a.name for a in accounts}
        category_options = {c.id: c.name for c in all_categories}

        # ── Builder state ──────────────────────────────────────────────────────
        state: dict[str, Any] = {
            "dimension": "category",
            "metric": "sum",
            "chart_type": "bar",
            "transaction_types": ["expense"],
            "date_preset": "this_year",
            "date_from": "",
            "date_to": "",
            "account_ids": [],
            "category_ids": [],
            "top_n": 10,
            "dragging": None,  # field key being dragged
            "dragging_grp": None,  # "dimension" or "metric"
            "result": None,  # last ReportResult
            "running": False,
            "error": None,
        }

        # ── Run report ─────────────────────────────────────────────────────────
        async def _run() -> None:
            state["running"] = True
            state["error"] = None
            chart_zone.refresh()
            config = ReportConfig(
                dimension=state["dimension"],
                metric=state["metric"],
                chart_type=state["chart_type"],
                transaction_types=state["transaction_types"],
                date_preset=state["date_preset"],
                date_from=state["date_from"] or None,
                date_to=state["date_to"] or None,
                account_ids=state["account_ids"],
                category_ids=state["category_ids"],
                top_n=int(state["top_n"] or 0) or None,
            )
            try:
                async with AsyncSessionFactory() as session:
                    result = await SavedReportService(session).execute(config)
                state["result"] = result
            except Exception as exc:  # noqa: BLE001
                state["error"] = str(exc)
            finally:
                state["running"] = False
            chart_zone.refresh()

        # ── Save report ────────────────────────────────────────────────────────
        async def _save(name: str) -> None:
            if not name.strip():
                ui.notify(t("reports.name_required"), type="warning")
                return
            config = ReportConfig(
                dimension=state["dimension"],
                metric=state["metric"],
                chart_type=state["chart_type"],
                transaction_types=state["transaction_types"],
                date_preset=state["date_preset"],
                date_from=state["date_from"] or None,
                date_to=state["date_to"] or None,
                account_ids=state["account_ids"],
                category_ids=state["category_ids"],
                top_n=int(state["top_n"] or 0) or None,
            )
            async with AsyncSessionFactory() as session:
                await SavedReportService(session).create(
                    SavedReportCreate(name=name.strip(), config=json.dumps(config.to_dict()))
                )
            ui.notify(t("reports.saved_ok"), type="positive")
            saved_section.refresh()

        # ── Load saved report into builder ─────────────────────────────────────
        async def _load(report_id: int) -> None:
            async with AsyncSessionFactory() as session:
                report = await SavedReportService(session).get(report_id)
            if not report:
                return
            cfg = ReportConfig.from_dict(json.loads(report.config))
            state.update(
                dimension=cfg.dimension,
                metric=cfg.metric,
                chart_type=cfg.chart_type,
                transaction_types=list(cfg.transaction_types),
                date_preset=cfg.date_preset,
                date_from=cfg.date_from or "",
                date_to=cfg.date_to or "",
                account_ids=list(cfg.account_ids),
                category_ids=list(cfg.category_ids),
                top_n=cfg.top_n,
            )
            palette_zone.refresh()
            config_zone.refresh()
            await _run()

        async def _delete(report_id: int) -> None:
            async with AsyncSessionFactory() as session:
                await SavedReportService(session).delete(report_id)
            ui.notify(t("reports.deleted"), type="positive")
            saved_section.refresh()

        # ── Drag-and-drop handlers ─────────────────────────────────────────────
        def _on_dragstart(key: str, grp: str) -> None:
            state["dragging"] = key
            state["dragging_grp"] = grp

        def _drop_dimension() -> None:
            if state["dragging_grp"] == "dimension":
                state["dimension"] = state["dragging"]
            state["dragging"] = None
            state["dragging_grp"] = None
            palette_zone.refresh()
            config_zone.refresh()

        def _drop_metric() -> None:
            if state["dragging_grp"] == "metric":
                state["metric"] = state["dragging"]
            state["dragging"] = None
            state["dragging_grp"] = None
            palette_zone.refresh()
            config_zone.refresh()

        # ══════════════════════════════════════════════════════════════════════
        with page_layout(t("reports.title")):
            ui.label(t("reports.title")).classes("text-2xl font-bold")

            # ── Saved reports row ──────────────────────────────────────────────
            @ui.refreshable
            async def saved_section() -> None:
                async with AsyncSessionFactory() as s:
                    reports = await SavedReportService(s).list()
                if not reports:
                    return
                ui.label(t("reports.saved")).classes("text-sm font-semibold text-grey-6 mt-4 mb-2")
                with ui.row().classes("gap-2 flex-wrap mb-2"):
                    for r in reports:
                        cfg_dict = json.loads(r.config)
                        icon = _chart_icon(cfg_dict.get("chart_type", "bar"))
                        with (
                            ui.card().classes("p-2 cursor-pointer hover:shadow-md"),
                            ui.row().classes("items-center gap-1 no-wrap"),
                        ):
                            ui.icon(icon, color="primary").classes("text-base")
                            ui.label(r.name).classes("text-sm font-medium")
                            ui.button(
                                icon="play_arrow",
                                on_click=lambda rid=r.id: _load(rid),
                            ).props("flat dense round size=xs color=primary").tooltip(
                                t("reports.run")
                            )
                            ui.button(
                                icon="delete",
                                on_click=lambda rid=r.id: _delete(rid),
                            ).props("flat dense round size=xs color=negative").tooltip(
                                t("common.delete")
                            )

            await saved_section()

            ui.separator().classes("my-4")

            # ── Builder ────────────────────────────────────────────────────────
            ui.label(t("reports.builder_title")).classes("text-lg font-semibold mb-3")

            with ui.row().classes("w-full gap-4 items-start"):
                # ──── Left: Palette ────────────────────────────────────────────
                @ui.refreshable
                def palette_zone() -> None:
                    with ui.card().classes("p-4 w-60 flex-shrink-0"):
                        ui.label(t("reports.dimensions")).classes(
                            "text-xs font-bold text-grey-6 uppercase tracking-wide mb-2"
                        )
                        for key, label_key, icon in _DIMENSIONS:
                            is_active = state["dimension"] == key
                            chip_cls = "cursor-grab mb-1 w-full justify-start " + (
                                "opacity-100" if is_active else "opacity-70 hover:opacity-100"
                            )
                            with ui.row().classes("w-full"):
                                chip = (
                                    ui.chip(
                                        t(label_key),
                                        icon=icon,
                                        color="primary" if is_active else "grey-7",
                                    )
                                    .classes(chip_cls)
                                    .props("draggable=true")
                                )
                                chip.on(
                                    "dragstart",
                                    lambda k=key: _on_dragstart(k, "dimension"),
                                )
                                if is_active:
                                    ui.icon("check_circle", color="primary").classes("text-base")

                        ui.separator().classes("my-3")
                        ui.label(t("reports.measures")).classes(
                            "text-xs font-bold text-grey-6 uppercase tracking-wide mb-2"
                        )
                        for key, label_key, icon in _METRICS:
                            is_active = state["metric"] == key
                            chip_cls = "cursor-grab mb-1 w-full justify-start " + (
                                "opacity-100" if is_active else "opacity-70 hover:opacity-100"
                            )
                            with ui.row().classes("w-full"):
                                chip = (
                                    ui.chip(
                                        t(label_key),
                                        icon=icon,
                                        color="secondary" if is_active else "grey-7",
                                    )
                                    .classes(chip_cls)
                                    .props("draggable=true")
                                )
                                chip.on(
                                    "dragstart",
                                    lambda k=key: _on_dragstart(k, "metric"),
                                )
                                if is_active:
                                    ui.icon("check_circle", color="secondary").classes("text-base")

                palette_zone()

                # ──── Right: Config + Chart ────────────────────────────────────
                with ui.element("div").classes("flex-1 min-w-0"):

                    @ui.refreshable
                    def config_zone() -> None:
                        hdr_cls = "text-xs font-bold text-grey-6 uppercase tracking-wide mb-2"

                        # ── Drop zones row ─────────────────────────────────────
                        with ui.row().classes("gap-4 mb-4 flex-wrap"):
                            # Group By drop zone
                            dz_dim_cls = (
                                "p-3 rounded-lg border-2 border-dashed min-w-40 cursor-pointer "
                                "border-primary bg-primary-50"
                            )
                            with (
                                ui.element("div")
                                .classes(dz_dim_cls)
                                .props('ondragover="event.preventDefault()"') as dz_dim
                            ):
                                dz_dim.on("drop", _drop_dimension)
                                ui.label(t("reports.group_by")).classes(hdr_cls)
                                dim_label = next(
                                    (t(lk) for k, lk, _ in _DIMENSIONS if k == state["dimension"]),
                                    "—",
                                )
                                dim_icon = next(
                                    (ic for k, _, ic in _DIMENSIONS if k == state["dimension"]),
                                    "category",
                                )
                                with ui.row().classes("items-center gap-1"):
                                    ui.icon(dim_icon, color="primary")
                                    ui.label(dim_label).classes("font-semibold text-primary")
                                ui.label(t("reports.drop_here")).classes("text-xs text-grey-5 mt-1")

                            # Measure drop zone
                            dz_met_cls = (
                                "p-3 rounded-lg border-2 border-dashed min-w-40 cursor-pointer "
                                "border-secondary bg-secondary-50"
                            )
                            with (
                                ui.element("div")
                                .classes(dz_met_cls)
                                .props('ondragover="event.preventDefault()"') as dz_met
                            ):
                                dz_met.on("drop", _drop_metric)
                                ui.label(t("reports.measure")).classes(hdr_cls)
                                met_label = next(
                                    (t(lk) for k, lk, _ in _METRICS if k == state["metric"]),
                                    "—",
                                )
                                met_icon = next(
                                    (ic for k, _, ic in _METRICS if k == state["metric"]),
                                    "functions",
                                )
                                with ui.row().classes("items-center gap-1"):
                                    ui.icon(met_icon, color="secondary")
                                    ui.label(met_label).classes("font-semibold text-secondary")
                                ui.label(t("reports.drop_here")).classes("text-xs text-grey-5 mt-1")

                        # ── Chart type selector ────────────────────────────────
                        with ui.row().classes("items-center gap-2 mb-4 flex-wrap"):
                            ui.label(t("reports.chart_type")).classes(hdr_cls + " my-0")
                            for ct, icon in _CHART_TYPES:
                                active = state["chart_type"] == ct
                                (
                                    ui.button(icon=icon, on_click=lambda c=ct: _set_chart(c))
                                    .props(
                                        f"{'color=primary' if active else 'outline color=grey-7'} "
                                        "round dense"
                                    )
                                    .tooltip(ct.capitalize())
                                )

                        # ── Filters ────────────────────────────────────────────
                        exp = ui.expansion(t("reports.filters"), icon="filter_list")
                        exp.classes("w-full mb-4")
                        with exp, ui.element("div").classes("flex flex-col gap-3 pt-2"):
                            # Transaction types
                            ui.label(t("reports.tx_types")).classes(hdr_cls)
                            with ui.row().classes("gap-2"):
                                for tk, tlk, tic, tcol in _TX_TYPES:
                                    active = tk in state["transaction_types"]
                                    ui.button(
                                        t(tlk),
                                        icon=tic,
                                        on_click=lambda k=tk: _toggle_type(k),
                                    ).props(
                                        (f"color={tcol}" if active else "outline color=grey-7")
                                        + " dense rounded"
                                    )

                            # Date preset
                            ui.label(t("reports.date_range")).classes(hdr_cls)
                            preset_opts = {k: t(lk) for k, lk in _DATE_PRESETS}
                            ui.select(
                                preset_opts,
                                value=state["date_preset"],
                                on_change=lambda e: (
                                    state.update(date_preset=e.value) or config_zone.refresh()
                                ),
                            ).classes("w-56")
                            if state["date_preset"] == "custom":
                                with ui.row().classes("gap-3"):
                                    ui.input(
                                        t("transactions.date_from"),
                                        value=state["date_from"],
                                        on_change=lambda e: state.update(date_from=e.value),
                                    ).props("type=date").classes("w-44")
                                    ui.input(
                                        t("transactions.date_to"),
                                        value=state["date_to"],
                                        on_change=lambda e: state.update(date_to=e.value),
                                    ).props("type=date").classes("w-44")

                            # Top N
                            ui.label(t("reports.top_n")).classes(hdr_cls)
                            ui.number(
                                t("reports.top_n_hint"),
                                value=state["top_n"],
                                min=0,
                                max=100,
                                step=5,
                                on_change=lambda e: state.update(top_n=int(e.value or 0)),
                            ).classes("w-32").props("dense")

                            # Accounts filter
                            if account_options:
                                ui.label(t("reports.filter_accounts")).classes(hdr_cls)
                                ui.select(
                                    account_options,
                                    multiple=True,
                                    value=state["account_ids"],
                                    label=t("reports.all_accounts"),
                                    on_change=lambda e: state.update(account_ids=e.value or []),
                                ).classes("w-full").props("use-chips")

                            # Categories filter
                            if category_options:
                                ui.label(t("reports.filter_categories")).classes(hdr_cls)
                                ui.select(
                                    category_options,
                                    multiple=True,
                                    value=state["category_ids"],
                                    label=t("reports.all_categories"),
                                    on_change=lambda e: state.update(  # noqa: E501
                                        category_ids=e.value or []
                                    ),
                                ).classes("w-full").props("use-chips")

                    def _set_chart(ct: str) -> None:
                        state["chart_type"] = ct
                        config_zone.refresh()
                        if state["result"]:
                            chart_zone.refresh()

                    def _toggle_type(tk: str) -> None:
                        if tk in state["transaction_types"]:
                            if len(state["transaction_types"]) > 1:
                                state["transaction_types"].remove(tk)
                        else:
                            state["transaction_types"].append(tk)
                        config_zone.refresh()

                    config_zone()

                    # ── Run & Save row ─────────────────────────────────────────
                    save_name_ref: list[ui.input] = []
                    with ui.row().classes("items-center gap-3 mb-4 flex-wrap"):
                        name_inp = ui.input(
                            t("reports.report_name"),
                            placeholder=t("reports.name_placeholder"),
                        ).classes("flex-1 min-w-40")
                        save_name_ref.append(name_inp)
                        ui.button(t("reports.run"), icon="play_arrow", on_click=_run).props(
                            "color=primary"
                        )
                        ui.button(
                            t("reports.save"),
                            icon="save",
                            on_click=lambda: _save(name_inp.value or ""),
                        ).props("outline color=primary")

                    # ── Chart zone ─────────────────────────────────────────────
                    @ui.refreshable
                    def chart_zone() -> None:
                        if state["running"]:
                            with ui.row().classes("items-center gap-2 h-64 justify-center w-full"):
                                ui.spinner(size="xl")
                                ui.label(t("common.loading"))
                            return
                        if state["error"]:
                            ui.label(f"Error: {state['error']}").classes("text-negative")
                            return
                        result = state["result"]
                        if result is None:
                            with (
                                ui.element("div").classes(
                                    "h-64 flex items-center justify-center text-grey-5 "
                                    "border-2 border-dashed rounded-lg w-full"
                                ),
                                ui.column().classes("items-center gap-2"),
                            ):
                                ui.icon("bar_chart").classes("text-5xl")
                                ui.label(t("reports.run_to_preview"))
                            return
                        if not result.labels:
                            ui.label(t("reports.no_data")).classes(
                                "text-grey-5 text-center py-8 w-full"
                            )
                            return

                        ct = state["chart_type"]
                        if ct == "table":
                            _render_table(result)
                        else:
                            option = build_echart_option(result, ct, is_dark)
                            ui.echart(option).classes("w-full").style("height: 380px")

                    chart_zone()

        def _render_table(result: ReportResult) -> None:
            r = result
            cols = [
                {"name": "label", "label": r.column_header, "field": "label", "align": "left"},
                {"name": "value", "label": r.metric_header, "field": "value", "align": "right"},
            ]
            rows = [
                {"label": lbl, "value": f"{v:,.2f}"}
                for lbl, v in zip(r.labels, r.values, strict=False)
            ]
            ui.table(columns=cols, rows=rows).classes("w-full").props("flat dense")
