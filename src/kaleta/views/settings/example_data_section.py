# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — Data tab, the Example data section.

One button per feature and one for the lot. Every one of them is safe to press
twice: the seeders in :mod:`kaleta.seeders` own their own rows and skip a
feature that already has example data, and the section says how many rows each
feature holds so the skip is never a surprise.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.seeders import SEEDERS
from kaleta.services import with_session
from kaleta.services.data_service import DataService
from kaleta.views.error_handling import notify_kaleta_error


async def render_example_data_section() -> None:
    """The card, with a live row count beside every button."""
    with ui.card().classes("p-6 w-full mt-4"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("dataset", color="primary").classes("text-xl")
            ui.label(t("settings.example_data_title")).classes("text-lg font-semibold")
        ui.label(t("settings.example_data_hint")).classes("text-xs text-slate-500 mb-4")

        pending: dict[str, list[str]] = {"keys": []}

        confirm_dlg = ui.dialog()
        with confirm_dlg, ui.card().classes("w-96"):
            ui.label(t("settings.example_data_confirm_title")).classes(
                "text-base font-semibold mb-1"
            )
            confirm_body = ui.label("").classes("text-sm text-slate-600 mb-4")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("common.cancel"), on_click=confirm_dlg.close).props("flat")
                confirm_btn = ui.button(
                    t("settings.example_data_confirm_btn"),
                    icon="dataset",
                ).props("color=primary unelevated")

        @ui.refreshable
        async def buttons() -> None:
            async def _load(session: Any) -> dict[str, int]:
                return await DataService(session).seed_status()

            status = await with_session(_load)

            def _ask(keys: list[str], label: str) -> None:
                pending["keys"] = keys
                filled = [key for key in keys if status.get(key, 0) > 0]
                if filled:
                    names = ", ".join(
                        t(f"settings.example_data_{key}") + f" ({status[key]})" for key in filled
                    )
                    confirm_body.set_text(t("settings.example_data_confirm_skip", names=names))
                else:
                    confirm_body.set_text(t("settings.example_data_confirm_body", feature=label))
                confirm_dlg.open()

            all_label = t("settings.example_data_all")
            with ui.row().classes("gap-3 flex-wrap mb-4"):
                ui.button(
                    all_label,
                    icon="auto_awesome",
                    on_click=lambda: _ask([seeder.key for seeder in SEEDERS], all_label),
                ).props("color=primary unelevated")

            with ui.column().classes("gap-1 w-full"):
                for seeder in SEEDERS:
                    label = t(seeder.label_key)
                    rows = status.get(seeder.key, 0)
                    with ui.row().classes("w-full items-center gap-3"):
                        ui.button(
                            label,
                            icon=seeder.icon,
                            on_click=lambda key=seeder.key, name=label: _ask([key], name),
                        ).props("outline color=primary dense").classes("w-56 justify-start")
                        ui.label(
                            t("settings.example_data_rows", count=rows)
                            if rows
                            else t("settings.example_data_empty")
                        ).classes("text-xs text-slate-500")

        async def _seed() -> None:
            keys = list(pending["keys"])
            confirm_dlg.close()
            if not keys:
                return
            notif = ui.notification(t("settings.seeding"), spinner=True, timeout=0)
            try:

                async def _run(session: Any) -> list[Any]:
                    return await DataService(session).seed_features(keys)

                outcomes = await with_session(_run)
                notif.dismiss()
                written = sum(outcome.total for outcome in outcomes if not outcome.skipped)
                skipped = [outcome.key for outcome in outcomes if outcome.skipped]
                if written:
                    ui.notify(t("settings.example_data_done", rows=written), type="positive")
                elif skipped:
                    ui.notify(t("settings.example_data_nothing_to_do"), type="info")
                buttons.refresh()
            except KaletaError as exc:
                notif.dismiss()
                notify_kaleta_error(exc)
            except Exception as exc:
                notif.dismiss()
                ui.notify(f"{t('settings.seed_error')}: {exc}", type="negative")

        confirm_btn.on_click(_seed)
        await buttons()
