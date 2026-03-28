from __future__ import annotations

import datetime
import functools
import json
from decimal import Decimal, InvalidOperation

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import available_languages, t
from kaleta.models.audit_log import MAX_AUDIT_ENTRIES
from kaleta.models.currency_rate import CurrencyRate
from kaleta.schemas.currency_rate import CurrencyRateCreate
from kaleta.services import AccountService, AuditService, BackupService
from kaleta.services.currency_rate_service import CurrencyRateService
from kaleta.services.data_service import DataService
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
                                    {"name": "date", "label": t("common.date"),
                                     "field": "date", "align": "left"},
                                    {"name": "pair", "label": t("settings.rate_pair"),
                                     "field": "pair", "align": "left"},
                                    {"name": "rate", "label": t("settings.rate_value"),
                                     "field": "rate", "align": "right"},
                                    {"name": "actions", "label": "",
                                     "field": "id", "align": "right"},
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
                            value=foreign_currencies[0] if foreign_currencies else COMMON_CURRENCIES[1],  # noqa: E501
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

            # ── Demo data ─────────────────────────────────────────────────────
            with ui.card().classes("p-6 w-full mt-4"):
                with ui.row().classes("items-center gap-2 mb-1"):
                    ui.icon("science", color="primary").classes("text-xl")
                    ui.label(t("settings.data_title")).classes("text-lg font-semibold")
                ui.label(t("settings.data_hint")).classes("text-xs text-grey-6 mb-4")

                # Define handlers first — dialogs are assigned below and captured
                # by closure (Python looks them up at call time, not definition time).
                async def _do_seed() -> None:
                    seed_dlg.close()
                    notif = ui.notification(t("settings.seeding"), spinner=True, timeout=0)
                    try:
                        async with AsyncSessionFactory() as s:
                            stats = await DataService(s).seed()
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
                    clear_data_dlg.close()
                    notif = ui.notification(t("settings.clearing"), spinner=True, timeout=0)
                    try:
                        async with AsyncSessionFactory() as s:
                            await DataService(s).clear_all()
                        notif.dismiss()
                        ui.notify(t("settings.clear_done"), type="positive")
                    except Exception as exc:
                        notif.dismiss()
                        ui.notify(f"{t('settings.clear_error')}: {exc}", type="negative")

                # ── seed confirm dialog ────────────────────────────────────────
                seed_dlg = ui.dialog()
                with seed_dlg, ui.card().classes("w-96"):
                    ui.label(t("settings.seed_confirm_title")).classes(
                        "text-base font-semibold mb-1"
                    )
                    ui.label(t("settings.seed_confirm_body")).classes(
                        "text-sm text-grey-7 mb-4"
                    )
                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button(t("common.cancel"), on_click=seed_dlg.close).props("flat")
                        ui.button(
                            t("settings.seed_btn"),
                            icon="science",
                            on_click=_do_seed,
                        ).props("color=primary unelevated")

                # ── clear confirm dialog ───────────────────────────────────────
                clear_data_dlg = ui.dialog()
                with clear_data_dlg, ui.card().classes("w-96"):
                    ui.label(t("settings.clear_confirm_title")).classes(
                        "text-base font-semibold mb-1"
                    )
                    ui.label(t("settings.clear_confirm_body")).classes(
                        "text-sm text-negative mb-4"
                    )
                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button(t("common.cancel"), on_click=clear_data_dlg.close).props(
                            "flat"
                        )
                        ui.button(
                            t("settings.clear_btn"),
                            icon="delete_forever",
                            on_click=_do_clear_data,
                        ).props("color=negative unelevated")

                with ui.row().classes("gap-3"):
                    ui.button(
                        t("settings.seed_btn"), icon="science", on_click=seed_dlg.open
                    ).props("color=primary")
                    ui.button(
                        t("settings.clear_btn"),
                        icon="delete_forever",
                        on_click=clear_data_dlg.open,
                    ).props("outline color=negative")

            # ── Change History ────────────────────────────────────────────────
            with ui.card().classes("p-6 w-full mt-4"):
                with ui.row().classes("items-center justify-between mb-1"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("history", color="primary").classes("text-xl")
                        ui.label(t("audit.title")).classes("text-lg font-semibold")
                    ui.button(
                        t("audit.clear"), icon="delete_sweep", on_click=lambda: _confirm_clear()
                    ).props("flat dense color=negative size=sm")
                ui.label(t("audit.hint", n=MAX_AUDIT_ENTRIES)).classes(
                    "text-xs text-grey-6 mb-4"
                )

                async def _do_revert(audit_id: int) -> None:
                    try:
                        async with AsyncSessionFactory() as s:
                            await AuditService(s).revert(audit_id)
                        ui.notify(t("audit.reverted_ok"), type="positive")
                        audit_history.refresh()
                    except Exception as exc:
                        ui.notify(t("audit.revert_failed", error=str(exc)), type="negative")

                async def _do_clear() -> None:
                    async with AsyncSessionFactory() as s:
                        await AuditService(s).clear()
                    ui.notify(t("audit.cleared"), type="positive")
                    clear_dlg.close()
                    audit_history.refresh()

                clear_dlg = ui.dialog()
                with clear_dlg, ui.card().classes("w-80"):
                    ui.label(t("audit.clear_confirm")).classes("text-base mb-4")
                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button(t("common.cancel"), on_click=clear_dlg.close).props("flat")
                        ui.button(t("audit.clear"), on_click=_do_clear).props("color=negative")

                def _confirm_clear() -> None:
                    clear_dlg.open()

                _op_color = {"INSERT": "positive", "UPDATE": "warning", "DELETE": "negative"}

                @ui.refreshable
                async def audit_history() -> None:
                    async with AsyncSessionFactory() as s:
                        entries = await AuditService(s).list()

                    if not entries:
                        ui.label(t("audit.empty")).classes("text-grey-5 text-sm")
                        return

                    # Column headers
                    with ui.row().classes(
                        "w-full px-2 py-1 text-xs text-grey-6 font-medium border-b"
                    ):
                        ui.label(t("audit.timestamp")).classes("w-40")
                        ui.label(t("audit.operation")).classes("w-28")
                        ui.label(t("audit.table")).classes("w-36")
                        ui.label(t("audit.record_id")).classes("w-16 text-right")
                        ui.label(t("audit.changes")).classes("flex-1")
                        ui.label("").classes("w-24")

                    for entry in entries:
                        op_label = t(f"audit.op_{entry.operation.lower()}")
                        color = _op_color.get(entry.operation, "grey")

                        if entry.operation == "UPDATE":
                            try:
                                keys = list(json.loads(entry.old_data or "{}").keys())
                                summary = ", ".join(keys[:6])
                                if len(keys) > 6:
                                    summary += f" +{len(keys) - 6}"
                            except Exception:
                                summary = "—"
                        elif entry.operation == "INSERT":
                            summary = t("audit.new_record")
                        else:
                            summary = t("audit.record_deleted")

                        row_cls = "w-full px-2 py-2 items-center border-b"
                        if entry.reverted:
                            row_cls += " opacity-50"

                        with ui.row().classes(row_cls):
                            ui.label(
                                entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                            ).classes("w-40 text-sm font-mono text-grey-7")
                            ui.badge(op_label, color=color).classes("w-28 text-center")
                            ui.label(entry.table_name).classes("w-36 text-sm")
                            ui.label(
                                str(entry.record_id) if entry.record_id is not None else "—"
                            ).classes("w-16 text-right text-sm text-grey-6")
                            ui.label(summary).classes(
                                "flex-1 text-sm text-grey-7 truncate"
                            )
                            with ui.row().classes("w-24 justify-end"):
                                if entry.reverted:
                                    ui.badge(t("audit.reverted"), color="grey").classes(
                                        "text-xs"
                                    )
                                else:
                                    ui.button(
                                        t("audit.revert"),
                                        on_click=functools.partial(_do_revert, entry.id),
                                    ).props("flat dense color=warning size=sm")

                await audit_history()
