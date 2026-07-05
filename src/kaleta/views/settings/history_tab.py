# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — History tab (audit log)."""

from __future__ import annotations

import functools
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import AuditService, with_session
from kaleta.services.audit_service import AuditEntryDisplay


def _format_changes_summary(entry: AuditEntryDisplay) -> str:
    if entry.operation == "UPDATE":
        if not entry.changed_fields:
            return "—"
        summary = ", ".join(entry.changed_fields[:6])
        if len(entry.changed_fields) > 6:
            summary += f" +{len(entry.changed_fields) - 6}"
        return summary
    if entry.operation == "INSERT":
        return t("audit.new_record")
    return t("audit.record_deleted")


async def render_history_tab() -> None:
    op_color = {"INSERT": "positive", "UPDATE": "warning", "DELETE": "negative"}

    clear_dlg = ui.dialog()

    with ui.card().classes("p-6 w-full"):
        with ui.row().classes("items-center justify-between mb-1"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("history", color="primary").classes("text-xl")
                ui.label(t("audit.title")).classes("text-lg font-semibold")
            ui.button(
                t("audit.clear"),
                icon="delete_sweep",
                on_click=clear_dlg.open,
            ).props("flat dense color=negative size=sm")
        ui.label(t("audit.hint", n=AuditService.MAX_ENTRIES)).classes("text-xs text-slate-500 mb-4")

        async def _do_revert(audit_id: int) -> None:
            try:

                async def _revert(session: Any) -> None:
                    await AuditService(session).revert(audit_id)

                await with_session(_revert)
                ui.notify(t("audit.reverted_ok"), type="positive")
                audit_history.refresh()
            except Exception as exc:
                ui.notify(t("audit.revert_failed", error=str(exc)), type="negative")

        async def _do_clear() -> None:

            async def _clear(session: Any) -> None:
                await AuditService(session).clear()

            await with_session(_clear)
            ui.notify(t("audit.cleared"), type="positive")
            clear_dlg.close()
            audit_history.refresh()

        with clear_dlg, ui.card().classes("w-80"):
            ui.label(t("audit.clear_confirm")).classes("text-base mb-4")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("common.cancel"), on_click=clear_dlg.close).props("flat")
                ui.button(t("audit.clear"), on_click=_do_clear).props("color=negative")

        @ui.refreshable
        async def audit_history() -> None:

            async def _load(session: Any) -> list[AuditEntryDisplay]:
                return await AuditService(session).list_for_display()

            entries = await with_session(_load)

            if not entries:
                ui.label(t("audit.empty")).classes("text-slate-400 text-sm")
                return

            with ui.row().classes("w-full px-2 py-1 text-xs text-slate-500 font-medium border-b"):
                ui.label(t("audit.timestamp")).classes("w-40")
                ui.label(t("audit.operation")).classes("w-28")
                ui.label(t("audit.table")).classes("w-36")
                ui.label(t("audit.record_id")).classes("w-16 text-right")
                ui.label(t("audit.changes")).classes("flex-1")
                ui.label("").classes("w-24")

            for entry in entries:
                op_label = t(f"audit.op_{entry.operation.lower()}")
                color = op_color.get(entry.operation, "grey")
                summary = _format_changes_summary(entry)

                row_cls = "w-full px-2 py-2 items-center border-b"
                if entry.reverted:
                    row_cls += " opacity-50"

                with ui.row().classes(row_cls):
                    ui.label(entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")).classes(
                        "w-40 text-sm font-mono text-slate-600"
                    )
                    ui.badge(op_label, color=color).classes("w-28 text-center")
                    ui.label(entry.table_name).classes("w-36 text-sm")
                    ui.label(str(entry.record_id) if entry.record_id is not None else "—").classes(
                        "w-16 text-right text-sm text-slate-500"
                    )
                    ui.label(summary).classes("flex-1 text-sm text-slate-600 truncate")
                    with ui.row().classes("w-24 justify-end"):
                        if entry.reverted:
                            ui.badge(t("audit.reverted"), color="grey").classes("text-xs")
                        else:
                            ui.button(
                                t("audit.revert"),
                                on_click=functools.partial(_do_revert, entry.id),
                            ).props("flat dense color=warning size=sm")

        await audit_history()
