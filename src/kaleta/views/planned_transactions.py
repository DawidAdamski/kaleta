from __future__ import annotations

import datetime
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.planned_transaction import (
    PlannedTransactionCreate,
    PlannedTransactionResponse,
    PlannedTransactionUpdate,
    RecurrenceFrequency,
)
from kaleta.schemas.transaction import TransactionType
from kaleta.services import AccountService, CategoryService, PlannedTransactionService, with_session
from kaleta.views.layout import page_layout
from kaleta.views.theme import AMOUNT_EXPENSE, AMOUNT_INCOME, AMOUNT_NEUTRAL, TABLE_SURFACE


def _freq_label(freq: RecurrenceFrequency, interval: int) -> str:
    base = t(f"planned.freq_{freq.value}")
    return base if interval == 1 else f"{t('planned.every')} {interval} × {base}"


def _type_color(tx_type: TransactionType) -> str:
    _map = {"income": "positive", "expense": "negative", "transfer": "info"}
    return _map.get(tx_type.value, "grey")


def register() -> None:
    @ui.page("/planned")
    async def planned_page() -> None:
        async def _load_refs(session: Any) -> tuple[dict[int, str], dict[int, str]]:
            accounts = await AccountService(session).list()
            cats_list = await CategoryService(session).list()
            return (
                {a.id: a.name for a in accounts},
                CategoryService.build_option_labels(cats_list),
            )

        account_opts, cat_opts = await with_session(_load_refs)

        # ── Shared form state ─────────────────────────────────────────────────
        edit_id: dict[str, int | None] = {"value": None}

        freq_opts = {
            RecurrenceFrequency.ONCE: t("planned.freq_once"),
            RecurrenceFrequency.DAILY: t("planned.freq_daily"),
            RecurrenceFrequency.WEEKLY: t("planned.freq_weekly"),
            RecurrenceFrequency.BIWEEKLY: t("planned.freq_biweekly"),
            RecurrenceFrequency.MONTHLY: t("planned.freq_monthly"),
            RecurrenceFrequency.QUARTERLY: t("planned.freq_quarterly"),
            RecurrenceFrequency.YEARLY: t("planned.freq_yearly"),
        }
        type_opts = {
            TransactionType.INCOME: t("common.income"),
            TransactionType.EXPENSE: t("common.expense"),
            TransactionType.TRANSFER: t("common.transfer"),
        }

        # ── Add / Edit dialog ─────────────────────────────────────────────────
        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[540px] gap-3"):
            dialog_title = ui.label("").classes("text-lg font-bold")

            name_input = ui.input(t("planned.name")).classes("w-full")

            with ui.row().classes("w-full gap-3"):
                account_sel = ui.select(account_opts, label=t("common.account")).classes("flex-1")
                type_sel = ui.select(
                    type_opts, label=t("common.type"), value=TransactionType.EXPENSE
                ).classes("flex-1")

            with ui.row().classes("w-full gap-3"):
                amount_input = ui.number(
                    t("common.amount"), min=0.01, step=0.01, precision=2
                ).classes("flex-1")
                category_sel = ui.select(
                    cat_opts, label=t("common.category"), clearable=True
                ).classes("flex-1")

            desc_input = (
                ui.textarea(t("common.description")).classes("w-full").props("rows=2 autogrow")
            )

            ui.separator()
            ui.label(t("planned.recurrence")).classes("text-sm font-semibold text-grey-7")

            with ui.row().classes("w-full gap-3 items-end"):
                freq_sel = ui.select(
                    freq_opts, label=t("planned.frequency"), value=RecurrenceFrequency.MONTHLY
                ).classes("flex-1")

                interval_row = ui.row().classes("flex-1 items-end")
                with interval_row:
                    interval_input = ui.number(
                        t("planned.interval"), value=1, min=1, step=1, precision=0
                    ).classes("w-full")

            def _on_freq_change(e: object) -> None:
                is_once = getattr(e, "value", None) == RecurrenceFrequency.ONCE
                interval_row.set_visibility(not is_once)

            freq_sel.on_value_change(_on_freq_change)

            with ui.row().classes("w-full gap-3"):
                start_input = (
                    ui.date(value=str(datetime.date.today()))
                    .classes("flex-1")
                    .props(f'label="{t("planned.start_date")}"')
                )
                end_input = (
                    ui.date().classes("flex-1").props(f'label="{t("planned.end_date")}" clearable')
                )

            active_toggle = ui.switch(t("planned.active"), value=True)

            async def _submit() -> None:
                name = (name_input.value or "").strip()
                if not name:
                    ui.notify(t("planned.name_required"), type="negative")
                    return
                if not account_sel.value:
                    ui.notify(t("planned.account_required"), type="negative")
                    return
                if not amount_input.value or float(amount_input.value) <= 0:
                    ui.notify(t("planned.amount_required"), type="negative")
                    return
                try:
                    s_date = datetime.date.fromisoformat(str(start_input.value).replace("/", "-"))
                except (ValueError, TypeError):
                    ui.notify(t("planned.start_required"), type="negative")
                    return
                e_date: datetime.date | None = None
                if end_input.value:
                    try:
                        e_date = datetime.date.fromisoformat(str(end_input.value).replace("/", "-"))
                    except (ValueError, TypeError):
                        e_date = None

                payload = PlannedTransactionCreate(
                    name=name,
                    amount=amount_input.value,
                    type=type_sel.value,
                    account_id=account_sel.value,
                    category_id=category_sel.value or None,
                    description=desc_input.value.strip() or None,
                    frequency=freq_sel.value,
                    interval=int(interval_input.value or 1),
                    start_date=s_date,
                    end_date=e_date,
                    is_active=active_toggle.value,
                )

                async def _save(session: Any) -> None:
                    svc = PlannedTransactionService(session)
                    if edit_id["value"] is None:
                        await svc.create(payload)
                        ui.notify(t("planned.created"), type="positive")
                    else:
                        await svc.update(
                            edit_id["value"],
                            PlannedTransactionUpdate(**payload.model_dump()),
                        )
                        ui.notify(t("planned.updated"), type="positive")

                await with_session(_save)

                dialog.close()
                planned_list_ui.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-1"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.save"), on_click=_submit).props("color=primary")
            ui.keyboard(
                on_key=lambda e: (
                    _submit()
                    if e.key == "Enter" and e.action.keydown
                    else dialog.close()
                    if e.key == "Escape" and e.action.keydown
                    else None
                )
            )

        # ── Delete dialog ─────────────────────────────────────────────────────
        del_id: dict[str, int | None] = {"value": None}
        del_dialog = ui.dialog()
        with del_dialog, ui.card().classes("w-[360px]"):
            del_label = ui.label("").classes("text-base")
            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=del_dialog.close).props("flat")

                async def _do_delete() -> None:
                    pid = del_id["value"]
                    if pid is not None:

                        async def _delete(session: Any) -> None:
                            await PlannedTransactionService(session).delete(pid)

                        await with_session(_delete)
                    ui.notify(t("planned.deleted"), type="positive")
                    del_dialog.close()
                    planned_list_ui.refresh()

                ui.button(t("common.delete"), icon="delete", on_click=_do_delete).props(
                    "color=negative"
                )

        # ── Helpers ───────────────────────────────────────────────────────────
        def _open_add() -> None:
            edit_id["value"] = None
            dialog_title.set_text(t("planned.add"))
            name_input.set_value("")
            account_sel.set_value(next(iter(account_opts), None))
            type_sel.set_value(TransactionType.EXPENSE)
            amount_input.set_value(None)
            category_sel.set_value(None)
            desc_input.set_value("")
            freq_sel.set_value(RecurrenceFrequency.MONTHLY)
            interval_input.set_value(1)
            interval_row.set_visibility(True)
            start_input.set_value(str(datetime.date.today()))
            end_input.set_value(None)
            active_toggle.set_value(True)
            dialog.open()

        def _open_edit(pt: PlannedTransactionResponse) -> None:
            edit_id["value"] = pt.id
            dialog_title.set_text(t("planned.edit"))
            name_input.set_value(pt.name)
            account_sel.set_value(pt.account_id)
            type_sel.set_value(pt.type)
            amount_input.set_value(float(pt.amount))
            category_sel.set_value(pt.category_id)
            desc_input.set_value(pt.description or "")
            freq_sel.set_value(pt.frequency)
            interval_input.set_value(pt.interval)
            interval_row.set_visibility(pt.frequency != RecurrenceFrequency.ONCE)
            start_input.set_value(str(pt.start_date))
            end_input.set_value(str(pt.end_date) if pt.end_date else None)
            active_toggle.set_value(pt.is_active)
            dialog.open()

        def _open_delete(pt: PlannedTransactionResponse) -> None:
            del_id["value"] = pt.id
            del_label.set_text(t("planned.delete_confirm", name=pt.name))
            del_dialog.open()

        async def _toggle(pt: PlannedTransactionResponse) -> None:
            async def _do_toggle(session: Any) -> None:
                await PlannedTransactionService(session).toggle_active(pt.id)

            await with_session(_do_toggle)
            planned_list_ui.refresh()

        # ── Planned list ──────────────────────────────────────────────────────
        @ui.refreshable
        async def planned_list_ui() -> None:
            async def _load(session: Any) -> list[dict[str, Any]]:
                svc = PlannedTransactionService(session)
                items = await svc.list()
                return [
                    {
                        "pt": PlannedTransactionResponse.model_validate(pt),
                        "account_name": pt.account.name if pt.account else "—",
                        "category_name": pt.category.name if pt.category else "—",
                        "next": svc.next_occurrence(pt),
                    }
                    for pt in items
                ]

            rows_data = await with_session(_load)

            if not rows_data:
                with ui.column().classes("w-full items-center py-20 gap-3 text-grey-5"):
                    ui.icon("event_repeat", size="4rem")
                    ui.label(t("planned.no_planned")).classes("text-lg")
                    ui.label(t("planned.no_planned_hint")).classes("text-sm")
                return

            def _col(name: str, label: str, align: str = "left") -> dict[str, str]:
                return {"name": name, "label": label, "field": name, "align": align}

            columns = [
                _col("name", t("planned.name")),
                _col("account", t("common.account")),
                _col("category", t("common.category")),
                _col("type", t("common.type")),
                _col("amount", t("common.amount"), "right"),
                _col("freq", t("planned.frequency")),
                _col("next", t("planned.next_occurrence")),
                _col("active", t("planned.active"), "center"),
                {"name": "actions", "label": "", "field": "actions", "align": "right"},
            ]

            rows = [
                {
                    "id": row["pt"].id,
                    "name": row["pt"].name,
                    "account": row["account_name"],
                    "category": row["category_name"],
                    "type": row["pt"].type.value,
                    "amount": (
                        f"+{abs(row['pt'].amount):,.2f}"
                        if row["pt"].type == TransactionType.INCOME
                        else f"-{abs(row['pt'].amount):,.2f}"
                    ),
                    "freq": _freq_label(row["pt"].frequency, row["pt"].interval),
                    "next": str(row["next"]) if row["next"] else "—",
                    "active": row["pt"].is_active,
                    "is_active": row["pt"].is_active,
                }
                for row in rows_data
            ]

            tbl = ui.table(columns=columns, rows=rows, row_key="id").classes(TABLE_SURFACE)
            tbl.props("flat")

            tbl.add_slot(
                "body-cell-type",
                '<q-td :props="props">'
                "<q-badge :color=\"props.row.type === 'income' ? 'positive' : "
                "props.row.type === 'expense' ? 'negative' : 'info'\" outline>"
                "{{ props.row.type }}</q-badge></q-td>",
            )
            tbl.add_slot(
                "body-cell-amount",
                '<q-td :props="props" class="text-right">'
                f"<span :class=\"props.row.type === 'income' ? '{AMOUNT_INCOME}' : "
                f"props.row.type === 'expense' ? '{AMOUNT_EXPENSE}' : '{AMOUNT_NEUTRAL}'\">"
                "{{ props.row.amount }}</span></q-td>",
            )
            tbl.add_slot(
                "body-cell-active",
                '<q-td :props="props" class="text-center">'
                "<q-icon :name=\"props.row.is_active ? 'check_circle' : 'pause_circle'\""
                " :color=\"props.row.is_active ? 'positive' : 'grey-5'\" size=\"1.2rem\" /></q-td>",
            )
            tbl.add_slot(
                "body-cell-actions",
                '<q-td :props="props" auto-width>'
                '<q-btn flat round dense icon="power_settings_new" size="sm"'
                " :color=\"props.row.is_active ? 'grey-6' : 'positive'\""
                " @click=\"$parent.$emit('toggle', props.row.id)\" />"
                '<q-btn flat round dense icon="edit" size="sm" color="primary"'
                " @click=\"$parent.$emit('edit', props.row.id)\" />"
                '<q-btn flat round dense icon="delete" size="sm" color="negative"'
                " @click=\"$parent.$emit('delete', props.row.id)\" /></q-td>",
            )

            pt_by_id = {row["pt"].id: row["pt"] for row in rows_data}

            async def _handle_toggle(e: Any) -> None:
                pt = pt_by_id.get(int(e.args)) if getattr(e, "args", None) is not None else None
                if pt:
                    await _toggle(pt)

            def _handle_edit(e: Any) -> None:
                pt = pt_by_id.get(int(e.args)) if getattr(e, "args", None) is not None else None
                if pt:
                    _open_edit(pt)

            def _handle_delete(e: Any) -> None:
                pt = pt_by_id.get(int(e.args)) if getattr(e, "args", None) is not None else None
                if pt:
                    _open_delete(pt)

            tbl.on("toggle", _handle_toggle)
            tbl.on("edit", _handle_edit)
            tbl.on("delete", _handle_delete)

        # ── Page ──────────────────────────────────────────────────────────────
        with page_layout(t("planned.title")):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("planned.title")).classes("text-2xl font-bold")
                with ui.row().classes("items-center gap-2"):
                    ui.button(
                        t("planned.calendar_view"),
                        icon="calendar_month",
                        on_click=lambda: ui.navigate.to("/payment-calendar"),
                    ).props("flat color=primary")
                    ui.button(t("planned.add"), icon="add", on_click=_open_add).props(
                        "color=primary"
                    )

            await planned_list_ui()
