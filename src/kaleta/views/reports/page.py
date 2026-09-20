# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reports builder page — routing, layout, and section wiring."""

from __future__ import annotations

import json
from typing import Any

from nicegui import app, ui

from kaleta.i18n import plural_key, t
from kaleta.schemas.report import SavedReportCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    SavedReportService,
    TransactionService,
    with_session,
)
from kaleta.services.saved_report_service import ReportConfig, report_config_from_builder_state
from kaleta.views.layout import page_layout
from kaleta.views.reports.chart_zone import build_chart_zone
from kaleta.views.reports.config_zone import build_config_zone
from kaleta.views.reports.constants import BUILDER_STATE_DEFAULTS
from kaleta.views.reports.palette import build_palette_zone
from kaleta.views.theme import (
    PAGE_CONTAINER,
    PAGE_EYEBROW,
    PAGE_FLUSH,
    PAGE_GAP_22,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_TITLE,
    TITLE_ACTION,
    TITLE_ACTION_PRIMARY,
)


async def reports_page() -> None:
    is_dark: bool = app.storage.user.get("dark_mode", False)

    async def _load_reference(session: Any) -> tuple[Any, Any, int]:
        accounts = await AccountService(session).list()
        categories = await CategoryService(session).list()
        # What the sentence is asking of: the eyebrow says how much ledger
        # there is before the reader spends a Run finding out.
        n_transactions = await TransactionService(session).count()
        return accounts, categories, n_transactions

    accounts, categories, n_transactions = await with_session(_load_reference)
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

    async def save_report(name: str) -> bool:
        """Save the current query. ``False`` when there was nothing to save."""
        if not name.strip():
            ui.notify(t("reports.name_required"), type="warning")
            return False
        config = report_config_from_builder_state(state)

        async def _create(session: Any) -> Any:
            return await SavedReportService(session).create(
                SavedReportCreate(name=name.strip(), config=json.dumps(config.to_dict()))
            )

        created = await with_session(_create)
        ui.notify(t("reports.saved_ok"), type="positive")
        # The id, not just the name: nothing stops two saved reports sharing
        # a name, and the header has to know which row it is standing for.
        state["report_id"] = created.id
        state["report_name"] = created.name
        header.refresh()
        palette_zone.refresh()
        return True

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
        state["report_id"] = report.id
        state["report_name"] = report.name
        header.refresh()
        palette_zone.refresh()
        config_zone.refresh()
        await run_report()

    async def delete_report(report_id: int) -> None:
        async def _delete(session: Any) -> None:
            await SavedReportService(session).delete(report_id)

        await with_session(_delete)
        ui.notify(t("reports.deleted"), type="positive")
        # Deleting the report that is open leaves the header naming a record
        # that no longer exists. Matched by id: two saved reports may share a
        # name, and the header stands for one row, not for a word.
        if state["report_id"] == report_id:
            state["report_id"] = None
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
            # A refused name keeps the dialog — and what was typed into it.
            if await save_report(name_inp.value or ""):
                save_dialog.close()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=save_dialog.close).props("flat")
            ui.button(t("common.save"), on_click=_save_and_close).props("color=primary")

    def _open_save() -> None:
        name_inp.set_value(state["report_name"] or "")
        save_dialog.open()

    def _eyebrow() -> str:
        """ "Unsaved report · 1 527 transactions in the ledger".

        The report's name moved off the title and onto the line above it:
        artboard `3e` titles the screen "Reports" and lets the eyebrow say
        which report is in hand, the way every other screen does.
        """
        which = state["report_name"] or t("reports.unsaved")
        scope = t(
            plural_key("reports.eyebrow_scope", n_transactions),
            count=f"{n_transactions:,}".replace(",", " "),
        )
        return f"{which} · {scope}"

    @ui.refreshable
    def header() -> None:
        with ui.row().classes("w-full items-end justify-between gap-4 flex-wrap"):
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(_eyebrow()).classes(PAGE_EYEBROW).props("data-page-eyebrow")
                ui.label(t("reports.title")).classes(PAGE_TITLE)
            with ui.row().classes("items-center gap-[9px]"):
                # The ink pill is the primary action, and on this screen that
                # is Run: artboard `3e` puts Save on the ink because it draws
                # a report that has already been run.
                ui.button(
                    t("reports.save"), icon="bookmark", on_click=_open_save, color=None
                ).props("flat no-caps dense").classes(TITLE_ACTION)
                ui.button(
                    t("reports.run"), icon="play_arrow", on_click=run_report, color=None
                ).props("flat no-caps dense").classes(TITLE_ACTION_PRIMARY)

    with page_layout(t("reports.title"), wide=True, container=f"{PAGE_CONTAINER} {PAGE_FLUSH}"):
        await palette_zone()
        with ui.column().classes(f"{PAGE_CONTAINER} {PAGE_GAP_22} flex-1 min-w-0"):
            header()
            with ui.card().classes(f"{SECTION_CARD} gap-0 w-full"):
                config_zone()
            with ui.card().classes(f"{SECTION_CARD} gap-0 w-full"):
                chart_zone()
