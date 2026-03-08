from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import available_languages, t
from kaleta.models.currency_rate import CurrencyRate
from kaleta.schemas.currency_rate import CurrencyRateCreate
from kaleta.services import AccountService, BackupService
from kaleta.services.currency_rate_service import CurrencyRateService
from kaleta.views.accounts import COMMON_CURRENCIES
from kaleta.views.layout import page_layout


def register() -> None:
    @ui.page("/settings")
    async def settings_page() -> None:
        async with AsyncSessionFactory() as session:
            accounts = await AccountService(session).list()
            rate_svc = CurrencyRateService(session)
            rate_pairs = await rate_svc.list_pairs()

        default_currency: str = app.storage.user.get("currency", "PLN")
        foreign_currencies = sorted(
            {a.currency for a in accounts if a.currency != default_currency}
        )
        # All pairs stored in DB that involve the default currency
        relevant_pairs = [
            (fc, tc)
            for (fc, tc) in rate_pairs
            if tc == default_currency
        ]
        # Also add pairs for foreign accounts not yet in DB
        existing_froms = {fc for (fc, _) in relevant_pairs}
        for cur in foreign_currencies:
            if cur not in existing_froms:
                relevant_pairs.append((cur, default_currency))

        with page_layout(t("settings.title")):
            ui.label(t("settings.title")).classes("text-2xl font-bold")

            with ui.row().classes("w-full gap-6 flex-wrap items-start"):
                # ── Language ──────────────────────────────────────────────────
                with ui.card().classes("p-6 min-w-72 w-80"):
                    with ui.row().classes("items-center gap-2 mb-4"):
                        ui.icon("language", color="primary").classes("text-xl")
                        ui.label(t("settings.language")).classes("text-lg font-semibold")

                    langs = available_languages()
                    current_lang: str = app.storage.user.get("language", "en")

                    def _set_language(lang: str) -> None:
                        app.storage.user["language"] = lang
                        ui.navigate.reload()

                    ui.select(
                        langs,
                        label=t("settings.language_label"),
                        value=current_lang,
                        on_change=lambda e: _set_language(e.value),
                    ).classes("w-full")
                    ui.label(t("settings.language_hint")).classes("text-xs text-grey-6 mt-2")

                # ── Default currency ──────────────────────────────────────────
                with ui.card().classes("p-6 min-w-72 w-80"):
                    with ui.row().classes("items-center gap-2 mb-4"):
                        ui.icon("currency_exchange", color="primary").classes("text-xl")
                        ui.label(t("settings.currency")).classes("text-lg font-semibold")

                    def _set_currency(currency: str) -> None:
                        app.storage.user["currency"] = currency
                        ui.navigate.reload()

                    ui.select(
                        COMMON_CURRENCIES,
                        label=t("settings.currency_label"),
                        value=default_currency,
                        on_change=lambda e: _set_currency(e.value),
                    ).classes("w-full")
                    ui.label(t("settings.currency_hint")).classes("text-xs text-grey-6 mt-2")

                # ── Exchange rate history ─────────────────────────────────────
                with ui.card().classes("p-6 min-w-96 flex-1"):
                    with ui.row().classes("items-center gap-2 mb-1"):
                        ui.icon("swap_horiz", color="primary").classes("text-xl")
                        ui.label(t("settings.exchange_rates")).classes("text-lg font-semibold")
                    ui.label(t("settings.exchange_rates_hint")).classes(
                        "text-xs text-grey-6 mb-4"
                    )

                    if not relevant_pairs and not foreign_currencies:
                        ui.label(t("settings.no_foreign_accounts")).classes(
                            "text-grey-5 text-sm"
                        )
                    else:
                        @ui.refreshable
                        async def rates_table() -> None:
                            async with AsyncSessionFactory() as s:
                                svc = CurrencyRateService(s)
                                # Load recent entries per pair (show last 5 per pair)
                                all_rows: list[CurrencyRate] = []
                                for fc, tc in relevant_pairs:
                                    rows = await svc.list_for_pair(fc, tc)
                                    all_rows.extend(rows[:5])
                            all_rows.sort(key=lambda r: r.date, reverse=True)

                            if not all_rows:
                                ui.label(t("settings.no_rates_yet")).classes(
                                    "text-grey-5 text-sm mb-3"
                                )
                            else:
                                cols = [
                                    {"name": "date", "label": t("common.date"), "field": "date", "align": "left"},
                                    {"name": "pair", "label": t("settings.rate_pair"), "field": "pair", "align": "left"},
                                    {"name": "rate", "label": t("settings.rate_value"), "field": "rate", "align": "right"},
                                    {"name": "actions", "label": "", "field": "id", "align": "right"},
                                ]
                                table_rows = [
                                    {
                                        "id": r.id,
                                        "date": str(r.date),
                                        "pair": f"1 {r.from_currency} = ? {r.to_currency}",
                                        "rate": f"{r.rate:.6f}",
                                    }
                                    for r in all_rows
                                ]
                                tbl = ui.table(
                                    columns=cols, rows=table_rows, row_key="id"
                                ).classes("w-full").props("flat dense")
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
                                    async with AsyncSessionFactory() as s:
                                        await CurrencyRateService(s).delete(rid)
                                    rates_table.refresh()

                                tbl.on("delete_rate", _delete_rate)

                        await rates_table()

                    # ── Add rate dialog ───────────────────────────────────────
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
                        dlg_date = ui.input(
                            t("common.date"),
                            value=str(datetime.date.today()),
                        ).props("type=date").classes("w-full")
                        dlg_also_inverse = ui.checkbox(
                            t("settings.also_store_inverse"), value=True
                        )

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
                            async with AsyncSessionFactory() as s:
                                svc = CurrencyRateService(s)
                                await svc.create(CurrencyRateCreate(
                                    date=on_date,
                                    from_currency=fc,
                                    to_currency=default_currency,
                                    rate=rate_val,
                                ))
                                if dlg_also_inverse.value:
                                    await svc.create(CurrencyRateCreate(
                                        date=on_date,
                                        from_currency=default_currency,
                                        to_currency=fc,
                                        rate=Decimal("1") / rate_val,
                                    ))
                            ui.notify(t("settings.rate_saved"), type="positive")
                            add_dlg.close()
                            rates_table.refresh()

                        with ui.row().classes("w-full justify-end gap-2 mt-3"):
                            ui.button(t("common.cancel"), on_click=add_dlg.close).props("flat")
                            ui.button(t("common.save"), on_click=_save_rate).props("color=primary")

                    ui.button(
                        t("settings.add_rate"), icon="add", on_click=add_dlg.open
                    ).props("flat color=primary").classes("mt-3")

            # ── Backup & Restore ──────────────────────────────────────────────
            with ui.card().classes("p-6 w-full mt-4"):
                with ui.row().classes("items-center gap-2 mb-1"):
                    ui.icon("backup", color="primary").classes("text-xl")
                    ui.label(t("settings.backup_title")).classes("text-lg font-semibold")
                ui.label(t("settings.backup_hint")).classes("text-xs text-grey-6 mb-4")

                async def _do_export() -> None:
                    async with AsyncSessionFactory() as s:
                        data = await BackupService(s).export()
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    ui.download(data, filename=f"kaleta_backup_{timestamp}.zip")
                    ui.notify(t("settings.backup_exported"), type="positive")

                # ── Restore dialog ────────────────────────────────────────────
                restore_dlg = ui.dialog()
                with restore_dlg, ui.card().classes("w-[480px]"):
                    ui.label(t("settings.restore_title")).classes("text-lg font-semibold mb-1")
                    ui.label(t("settings.restore_warning")).classes(
                        "text-sm text-negative mb-4"
                    )

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
                    ).props("accept=.zip flat bordered").classes("w-full mb-2")

                    async def _do_restore() -> None:
                        if not uploaded_bytes:
                            ui.notify(t("settings.restore_no_file"), type="warning")
                            return
                        restore_btn.disable()
                        try:
                            async with AsyncSessionFactory() as s:
                                counts = await BackupService(s).restore(uploaded_bytes[0])
                            total = sum(counts.values())
                            ui.notify(
                                t("settings.restore_done", total=total), type="positive"
                            )
                            restore_dlg.close()
                            ui.navigate.reload()
                        except Exception as exc:
                            ui.notify(
                                t("settings.restore_error", error=str(exc)), type="negative"
                            )
                            restore_btn.enable()

                    with ui.row().classes("w-full justify-end gap-2 mt-3"):
                        ui.button(t("common.cancel"), on_click=restore_dlg.close).props("flat")
                        restore_btn = ui.button(
                            t("settings.restore_confirm"), on_click=_do_restore
                        ).props("color=negative")
                        restore_btn.disable()

                with ui.row().classes("gap-3"):
                    ui.button(
                        t("settings.backup_export"), icon="download", on_click=_do_export
                    ).props("color=primary")
                    ui.button(
                        t("settings.backup_restore"), icon="upload", on_click=restore_dlg.open
                    ).props("outline color=negative")
