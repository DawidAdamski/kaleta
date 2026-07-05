# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reports builder page — routing, layout, and section wiring."""

from __future__ import annotations

import json
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.schemas.report import SavedReportCreate
from kaleta.services import AccountService, CategoryService, SavedReportService, with_session
from kaleta.services.saved_report_service import ReportConfig, report_config_from_builder_state
from kaleta.views.layout import page_layout
from kaleta.views.reports.chart_zone import build_chart_zone
from kaleta.views.reports.config_zone import build_config_zone
from kaleta.views.reports.constants import BUILDER_STATE_DEFAULTS
from kaleta.views.reports.palette import build_palette_zone
from kaleta.views.reports.saved_section import build_saved_section


async def reports_page() -> None:
    is_dark: bool = app.storage.user.get("dark_mode", False)

    async def _load_reference(session: Any) -> tuple[Any, Any]:
        accounts = await AccountService(session).list()
        categories = await CategoryService(session).list()
        return accounts, categories

    accounts, categories = await with_session(_load_reference)
    account_options = {account.id: account.name for account in accounts}
    category_options = CategoryService.build_option_labels(
        [category for category in categories if category.type.value == "expense"]
    )

    state: dict[str, Any] = dict(BUILDER_STATE_DEFAULTS)
    chart_zone = build_chart_zone(state, is_dark=is_dark)

    async def run_report() -> None:
        state["running"] = True
        state["error"] = None
        chart_zone.refresh()
        config = report_config_from_builder_state(state)
        try:

            async def _execute(session: Any) -> Any:
                return await SavedReportService(session).execute(config)

            state["result"] = await with_session(_execute)
        except Exception as exc:  # noqa: BLE001
            state["error"] = str(exc)
        finally:
            state["running"] = False
        chart_zone.refresh()

    async def save_report(name: str) -> None:
        if not name.strip():
            ui.notify(t("reports.name_required"), type="warning")
            return
        config = report_config_from_builder_state(state)

        async def _create(session: Any) -> None:
            await SavedReportService(session).create(
                SavedReportCreate(name=name.strip(), config=json.dumps(config.to_dict()))
            )

        await with_session(_create)
        ui.notify(t("reports.saved_ok"), type="positive")
        saved_section.refresh()

    async def load_report(report_id: int) -> None:
        async def _get(session: Any) -> Any:
            return await SavedReportService(session).get(report_id)

        report = await with_session(_get)
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
        await run_report()

    async def delete_report(report_id: int) -> None:
        async def _delete(session: Any) -> None:
            await SavedReportService(session).delete(report_id)

        await with_session(_delete)
        ui.notify(t("reports.deleted"), type="positive")
        saved_section.refresh()

    def on_dragstart(key: str, grp: str) -> None:
        state["dragging"] = key
        state["dragging_grp"] = grp

    def drop_dimension() -> None:
        if state["dragging_grp"] == "dimension":
            state["dimension"] = state["dragging"]
        state["dragging"] = None
        state["dragging_grp"] = None
        palette_zone.refresh()
        config_zone.refresh()

    def drop_metric() -> None:
        if state["dragging_grp"] == "metric":
            state["metric"] = state["dragging"]
        state["dragging"] = None
        state["dragging_grp"] = None
        palette_zone.refresh()
        config_zone.refresh()

    def set_chart(chart_type: str) -> None:
        state["chart_type"] = chart_type
        config_zone.refresh()
        if state["result"]:
            chart_zone.refresh()

    def toggle_type(type_key: str) -> None:
        if type_key in state["transaction_types"]:
            if len(state["transaction_types"]) > 1:
                state["transaction_types"].remove(type_key)
        else:
            state["transaction_types"].append(type_key)
        config_zone.refresh()

    palette_zone = build_palette_zone(state, on_dragstart=on_dragstart)
    config_zone = build_config_zone(
        state,
        account_options=account_options,
        category_options=category_options,
        on_drop_dimension=drop_dimension,
        on_drop_metric=drop_metric,
        on_set_chart=set_chart,
        on_toggle_type=toggle_type,
    )
    saved_section = build_saved_section(on_load=load_report, on_delete=delete_report)

    with page_layout(t("reports.title")):
        ui.label(t("reports.title")).classes("text-2xl font-bold")
        await saved_section()
        ui.separator().classes("my-4")
        ui.label(t("reports.builder_title")).classes("text-lg font-semibold mb-3")

        with ui.row().classes("w-full gap-4 items-start"):
            palette_zone()
            with ui.element("div").classes("flex-1 min-w-0"):
                config_zone()
                with ui.row().classes("items-center gap-3 mb-4 flex-wrap"):
                    name_inp = ui.input(
                        t("reports.report_name"),
                        placeholder=t("reports.name_placeholder"),
                    ).classes("flex-1 min-w-40")
                    ui.button(t("reports.run"), icon="play_arrow", on_click=run_report).props(
                        "color=primary"
                    )
                    ui.button(
                        t("reports.save"),
                        icon="save",
                        on_click=lambda: save_report(name_inp.value or ""),
                    ).props("outline color=primary")
                chart_zone()
