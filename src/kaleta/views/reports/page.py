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
from kaleta.views.theme import BODY_MUTED, PAGE_TITLE, SECTION_CARD, SECTION_TITLE


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
        state["report_name"] = name.strip()
        header.refresh()
        palette_zone.refresh()

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
        state["report_name"] = report.name
        header.refresh()
        palette_zone.refresh()
        config_zone.refresh()
        await run_report()

    async def delete_report(report_id: int) -> None:
        async def _get_and_delete(session: Any) -> Any:
            service = SavedReportService(session)
            report = await service.get(report_id)
            await service.delete(report_id)
            return report

        deleted = await with_session(_get_and_delete)
        ui.notify(t("reports.deleted"), type="positive")
        # Deleting the report that is open leaves the header naming a record
        # that no longer exists — and the next Save would recreate it under
        # that name rather than asking for a new one.
        if deleted is not None and deleted.name == state["report_name"]:
            state["report_name"] = ""
            header.refresh()
        palette_zone.refresh()

    def on_dragstart(key: str, grp: str) -> None:
        """Remember what is being dragged. Deliberately no refresh.

        The slots light up through a body class the rail sets in the browser,
        not through a rebuild: repainting the sentence mid-drag destroys the
        very element the browser is aiming the drop at, and the drop is then
        never delivered.
        """
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

    def set_field(field: str, value: Any) -> None:
        """Every sentence slot and rail row lands here.

        The state the slots write is exactly the state the old selects and
        drop zones wrote, so a saved report round-trips through the sentence
        unchanged — which is the one thing this rewrite must not break.
        """
        state[field] = value
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

    palette_zone = build_palette_zone(
        state,
        on_dragstart=on_dragstart,
        on_set=set_field,
        on_load=load_report,
        on_delete=delete_report,
    )
    config_zone = build_config_zone(
        state,
        account_options=account_options,
        category_options=category_options,
        on_drop_dimension=drop_dimension,
        on_drop_metric=drop_metric,
        on_set_chart=set_chart,
        on_toggle_type=toggle_type,
        on_set=set_field,
    )

    save_dialog = ui.dialog()
    with save_dialog, ui.card().classes("w-96 gap-3"):
        ui.label(t("reports.save")).classes(SECTION_TITLE)
        name_inp = ui.input(
            t("reports.report_name"), placeholder=t("reports.name_placeholder")
        ).classes("w-full")

        async def _save_and_close() -> None:
            await save_report(name_inp.value or "")
            save_dialog.close()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=save_dialog.close).props("flat")
            ui.button(t("common.save"), on_click=_save_and_close).props("color=primary")

    def _open_save() -> None:
        name_inp.set_value(state["report_name"] or "")
        save_dialog.open()

    @ui.refreshable
    def header() -> None:
        with ui.row().classes("w-full items-center justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(state["report_name"] or t("reports.unsaved")).classes(PAGE_TITLE)
                ui.label(t("reports.builder_title")).classes(BODY_MUTED)
            with ui.row().classes("items-center gap-2"):
                ui.button(t("reports.run"), icon="play_arrow", on_click=run_report).props(
                    "color=primary unelevated"
                )
                ui.button(t("reports.save"), icon="save", on_click=_open_save).props(
                    "flat color=primary"
                )

    with page_layout(t("reports.title"), wide=True):
        header()
        with ui.row().classes("w-full gap-6 items-start flex-wrap lg:flex-nowrap"):
            await palette_zone()
            with ui.column().classes("flex-1 min-w-0 gap-4"):
                with ui.card().classes(f"{SECTION_CARD} gap-3"):
                    config_zone()
                with ui.card().classes(f"{SECTION_CARD} gap-2"):
                    chart_zone()
