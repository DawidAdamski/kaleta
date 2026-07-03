"""Settings — Data tab (exchange rates, backup, seed, wipe)."""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.currency_rate import CurrencyRateCreate, CurrencyRateResponse
from kaleta.services import BackupService, CurrencyRateService, with_session
from kaleta.services.data_service import DataService
from kaleta.views.accounts import COMMON_CURRENCIES


async def render_data_tab(
    *,
    default_currency: str,
    foreign_currencies: list[str],
    relevant_pairs: list[tuple[str, str]],
) -> None:
    with ui.card().classes("p-6 w-full"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("swap_horiz", color="primary").classes("text-xl")
            ui.label(t("settings.exchange_rates")).classes("text-lg font-semibold")
        ui.label(t("settings.exchange_rates_hint")).classes("text-xs text-grey-6 mb-4")

        if not relevant_pairs and not foreign_currencies:
            ui.label(t("settings.no_foreign_accounts")).classes("text-grey-5 text-sm")
        else:

            @ui.refreshable
            async def rates_table() -> None:
                async def _load_rates(session: Any) -> list[CurrencyRateResponse]:
                    return await CurrencyRateService(session).list_recent_for_pairs(relevant_pairs)

                all_rows = await with_session(_load_rates)

                if not all_rows:
                    ui.label(t("settings.no_rates_yet")).classes("text-grey-5 text-sm mb-3")
                else:
                    cols = [
                        {
                            "name": "date",
                            "label": t("common.date"),
                            "field": "date",
                            "align": "left",
                        },
                        {
                            "name": "pair",
                            "label": t("settings.rate_pair"),
                            "field": "pair",
                            "align": "left",
                        },
                        {
                            "name": "rate",
                            "label": t("settings.rate_value"),
                            "field": "rate",
                            "align": "right",
                        },
                        {
                            "name": "actions",
                            "label": "",
                            "field": "id",
                            "align": "right",
                        },
                    ]
                    table_rows = [
                        {
                            "id": row.id,
                            "date": str(row.date),
                            "pair": f"1 {row.from_currency} = ? {row.to_currency}",
                            "rate": f"{row.rate:.6f}",
                        }
                        for row in all_rows
                    ]
                    tbl = (
                        ui.table(columns=cols, rows=table_rows, row_key="id")
                        .classes("w-full")
                        .props("flat dense")
                    )
                    tbl.add_slot(
                        "body-cell-actions",
                        """
                        <q-td :props="props">
                          <q-btn flat dense round icon="delete" size="sm"
                                 color="negative"
                                 @click="$emit('delete_rate', props.row)" />
                        </q-td>
                        """,
                    )

                    async def _delete_rate(e: object) -> None:
                        rid = e.args["id"]  # type: ignore[attr-defined]

                        async def _delete(session: Any) -> None:
                            await CurrencyRateService(session).delete(rid)

                        await with_session(_delete)
                        rates_table.refresh()

                    tbl.on("delete_rate", _delete_rate)

            await rates_table()

        add_dlg = ui.dialog()
        with add_dlg, ui.card().classes("w-96"):
            ui.label(t("settings.add_rate")).classes("text-lg font-semibold mb-2")
            fc_options = {c: c for c in COMMON_CURRENCIES if c != default_currency}
            dlg_from = ui.select(
                fc_options,
                label=t("settings.rate_from_currency"),
                value=foreign_currencies[0] if foreign_currencies else COMMON_CURRENCIES[1],
            ).classes("w-full")
            dlg_rate = ui.number(
                t("settings.rate_value"),
                min=0.000001,
                format="%.6f",
                step=0.01,
            ).classes("w-full")
            dlg_date = (
                ui.input(t("common.date"), value=str(datetime.date.today()))
                .props("type=date")
                .classes("w-full")
            )
            dlg_also_inverse = ui.checkbox(t("settings.also_store_inverse"), value=True)

            async def _save_rate() -> None:
                try:
                    rate_val = Decimal(str(dlg_rate.value or 0))
                    if rate_val <= 0:
                        raise ValueError
                except (InvalidOperation, ValueError):
                    ui.notify(t("settings.rate_invalid"), type="negative")
                    return
                try:
                    on_date = datetime.date.fromisoformat(dlg_date.value or "")
                except ValueError:
                    on_date = datetime.date.today()
                fc = dlg_from.value or "EUR"

                async def _create(session: Any) -> None:
                    await CurrencyRateService(session).create_with_inverse(
                        CurrencyRateCreate(
                            date=on_date,
                            from_currency=fc,
                            to_currency=default_currency,
                            rate=rate_val,
                        ),
                        also_inverse=bool(dlg_also_inverse.value),
                    )

                await with_session(_create)
                ui.notify(t("settings.rate_saved"), type="positive")
                add_dlg.close()
                rates_table.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button(t("common.cancel"), on_click=add_dlg.close).props("flat")
                ui.button(t("common.save"), on_click=_save_rate).props("color=primary")

        ui.button(t("settings.add_rate"), icon="add", on_click=add_dlg.open).props(
            "flat color=primary"
        ).classes("mt-3")

    with ui.card().classes("p-6 w-full mt-4"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("backup", color="primary").classes("text-xl")
            ui.label(t("settings.backup_title")).classes("text-lg font-semibold")
        ui.label(t("settings.backup_hint")).classes("text-xs text-grey-6 mb-4")

        async def _do_export() -> None:
            async def _export(session: Any) -> bytes:
                return await BackupService(session).export()

            data = await with_session(_export)
            ui.download(data, filename=BackupService.export_filename())
            ui.notify(t("settings.backup_exported"), type="positive")

        restore_dlg = ui.dialog()
        with restore_dlg, ui.card().classes("w-[480px]"):
            ui.label(t("settings.restore_title")).classes("text-lg font-semibold mb-1")
            ui.label(t("settings.restore_warning")).classes("text-sm text-negative mb-4")

            uploaded_bytes: list[bytes] = []

            def _on_upload(e: object) -> None:
                content = e.content.read()  # type: ignore[attr-defined]
                uploaded_bytes.clear()
                uploaded_bytes.append(content)
                restore_btn.enable()
                ui.notify(t("settings.restore_file_ready"), type="info")

            ui.upload(
                label=t("settings.restore_select_file"),
                on_upload=_on_upload,
                auto_upload=True,
                max_file_size=100 * 1024 * 1024,
            ).props("accept=.zip flat bordered").classes("w-full mb-2")

            async def _do_restore() -> None:
                if not uploaded_bytes:
                    ui.notify(t("settings.restore_no_file"), type="warning")
                    return
                restore_btn.disable()
                try:

                    async def _restore(session: Any) -> dict[str, int]:
                        return await BackupService(session).restore(uploaded_bytes[0])

                    counts = await with_session(_restore)
                    total = sum(counts.values())
                    ui.notify(t("settings.restore_done", total=total), type="positive")
                    restore_dlg.close()
                    ui.navigate.reload()
                except Exception as exc:
                    ui.notify(t("settings.restore_error", error=str(exc)), type="negative")
                    restore_btn.enable()

            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button(t("common.cancel"), on_click=restore_dlg.close).props("flat")
                restore_btn = ui.button(t("settings.restore_confirm"), on_click=_do_restore).props(
                    "color=negative"
                )
                restore_btn.disable()

        with ui.row().classes("gap-3"):
            ui.button(t("settings.backup_export"), icon="download", on_click=_do_export).props(
                "color=primary"
            )
            ui.button(t("settings.backup_restore"), icon="upload", on_click=restore_dlg.open).props(
                "outline color=negative"
            )

    with ui.card().classes("p-6 w-full mt-4"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("science", color="primary").classes("text-xl")
            ui.label(t("settings.data_title")).classes("text-lg font-semibold")
        ui.label(t("settings.data_hint")).classes("text-xs text-grey-6 mb-4")

        async def _do_seed() -> None:
            seed_dlg.close()
            notif = ui.notification(t("settings.seeding"), spinner=True, timeout=0)
            try:

                async def _seed(session: Any) -> dict[str, int]:
                    return await DataService(session).seed()

                stats = await with_session(_seed)
                notif.dismiss()
                ui.notify(
                    t(
                        "settings.seed_done",
                        tx=stats["transactions"],
                        months=t("settings.seed_years"),
                    ),
                    type="positive",
                )
            except Exception as exc:
                notif.dismiss()
                ui.notify(f"{t('settings.seed_error')}: {exc}", type="negative")

        async def _do_clear_data() -> None:
            if (wipe_input.value or "").strip() != "DELETE":
                ui.notify(t("settings.clear_confirm_typo"), type="warning")
                return
            clear_data_dlg.close()
            notif = ui.notification(t("settings.clearing"), spinner=True, timeout=0)
            try:

                async def _clear(session: Any) -> None:
                    await DataService(session).clear_all()

                await with_session(_clear)
                notif.dismiss()
                ui.notify(t("settings.clear_done"), type="positive")
            except Exception as exc:
                notif.dismiss()
                ui.notify(f"{t('settings.clear_error')}: {exc}", type="negative")

        seed_dlg = ui.dialog()
        with seed_dlg, ui.card().classes("w-96"):
            ui.label(t("settings.seed_confirm_title")).classes("text-base font-semibold mb-1")
            ui.label(t("settings.seed_confirm_body")).classes("text-sm text-grey-7 mb-4")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("common.cancel"), on_click=seed_dlg.close).props("flat")
                ui.button(
                    t("settings.seed_btn"),
                    icon="science",
                    on_click=_do_seed,
                ).props("color=primary unelevated")

        clear_data_dlg = ui.dialog()
        with clear_data_dlg, ui.card().classes("w-96"):
            ui.label(t("settings.clear_confirm_title")).classes("text-base font-semibold mb-1")
            ui.label(t("settings.clear_confirm_body")).classes("text-sm text-negative mb-4")
            wipe_input = ui.input(label=t("settings.clear_confirm_typebox")).classes("w-full mb-2")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("common.cancel"), on_click=clear_data_dlg.close).props("flat")
                clear_btn = ui.button(
                    t("settings.clear_btn"),
                    icon="delete_forever",
                    on_click=_do_clear_data,
                ).props("color=negative unelevated")
            clear_btn.disable()

            def _update_wipe_confirm(e: object) -> None:
                typed = (getattr(e, "value", None) or "").strip()
                if typed == "DELETE":
                    clear_btn.enable()
                else:
                    clear_btn.disable()

            wipe_input.on_value_change(_update_wipe_confirm)

        with ui.row().classes("gap-3"):
            ui.button(t("settings.seed_btn"), icon="science", on_click=seed_dlg.open).props(
                "color=primary"
            )
            ui.button(
                t("settings.clear_btn"),
                icon="delete_forever",
                on_click=clear_data_dlg.open,
            ).props("outline color=negative")
