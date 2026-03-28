from __future__ import annotations

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.payee import Payee
from kaleta.schemas.payee import PayeeCreate, PayeeUpdate
from kaleta.services import PayeeService
from kaleta.views.layout import page_layout


def register() -> None:
    @ui.page("/payees")
    async def payees_page() -> None:

        # Mutable state
        dialog_payee_id: dict = {"value": None}
        delete_id: dict = {"value": None}
        selected_ids: list[int] = []

        # ── Add / Edit dialog ──────────────────────────────────────────────────
        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[520px] gap-3"):
            dialog_title = ui.label("").classes("text-lg font-bold")
            name_input = ui.input(t("payees.name")).classes("w-full").props("autofocus")

            with ui.expansion(t("payees.contact_details"), icon="contact_page").classes("w-full"):  # noqa: SIM117
                with ui.column().classes("w-full gap-2"):
                    website_input = ui.input(t("payees.website")).classes("w-full")
                    with ui.row().classes("w-full gap-2"):
                        address_input = ui.input(t("payees.address")).classes("flex-1")
                        city_input = ui.input(t("payees.city")).classes("w-32")
                    with ui.row().classes("w-full gap-2"):
                        country_input = ui.input(t("payees.country")).classes("flex-1")
                        phone_input = ui.input(t("payees.phone")).classes("flex-1")
                    email_input = ui.input(t("payees.email")).classes("w-full")

            notes_input = ui.textarea(
                t("payees.notes"),
                placeholder=t("payees.notes_hint"),
            ).classes("w-full").props("rows=3 autogrow")

            async def _submit() -> None:
                name = (name_input.value or "").strip()
                if not name:
                    ui.notify(t("payees.name_required"), type="negative")
                    return
                payload = PayeeCreate(
                    name=name,
                    website=(website_input.value or "").strip() or None,
                    address=(address_input.value or "").strip() or None,
                    city=(city_input.value or "").strip() or None,
                    country=(country_input.value or "").strip() or None,
                    email=(email_input.value or "").strip() or None,
                    phone=(phone_input.value or "").strip() or None,
                    notes=(notes_input.value or "").strip() or None,
                )
                async with AsyncSessionFactory() as session:
                    svc = PayeeService(session)
                    if dialog_payee_id["value"] is None:
                        await svc.create(payload)
                        ui.notify(t("payees.created"), type="positive")
                    else:
                        await svc.update(
                            dialog_payee_id["value"],
                            PayeeUpdate(**payload.model_dump()),
                        )
                        ui.notify(t("payees.updated"), type="positive")
                dialog.close()
                payees_list.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-1"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.save"), on_click=_submit).props("color=primary")
            ui.keyboard(on_key=lambda e: (
                _submit() if e.key == "Enter" and e.action.keydown else
                dialog.close() if e.key == "Escape" and e.action.keydown else None
            ))

        # ── Delete dialog ──────────────────────────────────────────────────────
        delete_dialog = ui.dialog()
        with delete_dialog, ui.card().classes("w-[400px]"):
            delete_label = ui.label("").classes("text-base")
            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")

                async def _do_delete() -> None:
                    if delete_id["value"] is not None:
                        async with AsyncSessionFactory() as session:
                            await PayeeService(session).delete(delete_id["value"])
                    ui.notify(t("payees.deleted"), type="positive")
                    delete_dialog.close()
                    payees_list.refresh()

                ui.button(
                    t("common.delete"), icon="delete", on_click=_do_delete
                ).props("color=negative")

        # ── Merge dialog ───────────────────────────────────────────────────────
        merge_state: dict = {"keep_id": None, "merge_ids": [], "payee_options": {}}

        merge_dialog = ui.dialog()
        with merge_dialog, ui.card().classes("w-[440px] gap-3"):
            ui.label(t("payees.merge_title")).classes("text-lg font-bold")
            ui.label(t("payees.merge_hint")).classes("text-sm text-grey-6")
            merge_keep_sel = ui.select(
                {}, label=t("payees.merge_keep")
            ).classes("w-full")
            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=merge_dialog.close).props("flat")

                async def _do_merge() -> None:
                    keep = merge_keep_sel.value
                    if keep is None:
                        ui.notify(t("payees.merge_keep_required"), type="negative")
                        return
                    merge_ids = [i for i in merge_state["merge_ids"] if i != keep]
                    async with AsyncSessionFactory() as session:
                        await PayeeService(session).merge(keep, merge_ids)
                    ui.notify(t("payees.merged"), type="positive")
                    selected_ids.clear()
                    merge_dialog.close()
                    payees_list.refresh()
                    selection_bar.refresh()

                ui.button(
                    t("payees.merge_confirm"), icon="merge", on_click=_do_merge
                ).props("color=primary")

        # ── Helpers ────────────────────────────────────────────────────────────
        def _open_add() -> None:
            dialog_payee_id["value"] = None
            dialog_title.set_text(t("payees.add"))
            name_input.set_value("")
            website_input.set_value("")
            address_input.set_value("")
            city_input.set_value("")
            country_input.set_value("")
            email_input.set_value("")
            phone_input.set_value("")
            notes_input.set_value("")
            dialog.open()

        def _open_edit(payee: Payee) -> None:
            dialog_payee_id["value"] = payee.id
            dialog_title.set_text(t("payees.edit"))
            name_input.set_value(payee.name)
            website_input.set_value(payee.website or "")
            address_input.set_value(payee.address or "")
            city_input.set_value(payee.city or "")
            country_input.set_value(payee.country or "")
            email_input.set_value(payee.email or "")
            phone_input.set_value(payee.phone or "")
            notes_input.set_value(payee.notes or "")
            dialog.open()

        def _open_delete(payee: Payee) -> None:
            delete_id["value"] = payee.id
            delete_label.set_text(t("payees.delete_confirm", name=payee.name))
            delete_dialog.open()

        def _open_merge(all_payees: list[Payee]) -> None:
            opts = {p.id: p.name for p in all_payees if p.id in selected_ids}
            merge_state["merge_ids"] = list(selected_ids)
            merge_state["payee_options"] = opts
            merge_keep_sel.options = opts
            merge_keep_sel.value = next(iter(opts)) if opts else None
            merge_dialog.open()

        # ── Selection action bar ───────────────────────────────────────────────
        @ui.refreshable
        def selection_bar() -> None:
            if len(selected_ids) >= 2:
                with ui.row().classes("w-full items-center gap-2 px-1 py-2 bg-blue-50 rounded"):
                    ui.label(
                        t("payees.selected_count", count=len(selected_ids))
                    ).classes("text-sm flex-1")
                    ui.button(
                        t("payees.merge"), icon="merge",
                        on_click=lambda: _open_merge_from_bar(),
                    ).props("color=primary dense")

        def _open_merge_from_bar() -> None:
            # need current payees list — captured via closure from payees_list
            _open_merge(_current_payees["list"])

        _current_payees: dict = {"list": []}

        # ── Payees list ────────────────────────────────────────────────────────
        @ui.refreshable
        async def payees_list() -> None:
            async with AsyncSessionFactory() as session:
                rows_with_counts = await PayeeService(session).list_with_counts()
            all_payees = [p for p, _ in rows_with_counts]
            _current_payees["list"] = all_payees

            if not all_payees:
                with ui.column().classes("w-full items-center py-20 gap-3 text-grey-5"):
                    ui.icon("person_off", size="4rem")
                    ui.label(t("payees.no_payees")).classes("text-lg")
                    ui.label(t("payees.no_payees_hint")).classes(
                        "text-sm text-center max-w-md"
                    )
                return

            tbl = (
                ui.table(
                    columns=[
                        {
                            "name": "name",
                            "label": t("payees.name"),
                            "field": "name",
                            "align": "left",
                            "sortable": True,
                        },
                        {
                            "name": "tx_count",
                            "label": t("payees.tx_count"),
                            "field": "tx_count",
                            "align": "right",
                        },
                        {
                            "name": "notes",
                            "label": t("payees.notes"),
                            "field": "notes",
                            "align": "left",
                        },
                        {
                            "name": "actions",
                            "label": "",
                            "field": "actions",
                            "align": "right",
                        },
                    ],
                    rows=[
                        {
                            "id": p.id,
                            "name": p.name,
                            "tx_count": cnt,
                            "notes": (p.notes or "")[:80],
                        }
                        for p, cnt in rows_with_counts
                    ],
                    row_key="id",
                )
                .classes("w-full")
                .props("flat bordered selection=multiple")
            )

            tbl.add_slot(
                "body-cell-actions",
                '<q-td :props="props" auto-width>'
                '<q-btn flat round dense icon="edit" color="primary" size="sm"'
                " @click=\"$parent.$emit('edit_p', props.row.id)\" />"
                '<q-btn flat round dense icon="delete" color="negative" size="sm"'
                " @click=\"$parent.$emit('delete_p', props.row.id)\" />"
                "</q-td>",
            )

            def _on_edit(e: object) -> None:
                pid = e.args  # type: ignore[attr-defined]
                payee = next((p for p in all_payees if p.id == pid), None)
                if payee:
                    _open_edit(payee)

            def _on_delete(e: object) -> None:
                pid = e.args  # type: ignore[attr-defined]
                payee = next((p for p in all_payees if p.id == pid), None)
                if payee:
                    _open_delete(payee)

            def _on_selection(e: object) -> None:
                rows_list = getattr(e, "args", None) or []
                selected_ids.clear()
                selected_ids.extend(r["id"] for r in rows_list)
                selection_bar.refresh()

            tbl.on("edit_p", _on_edit)
            tbl.on("delete_p", _on_delete)
            tbl.on("update:selected", _on_selection)

        # ── Page ───────────────────────────────────────────────────────────────
        with page_layout(t("payees.title")):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("payees.title")).classes("text-2xl font-bold")
                ui.button(
                    t("payees.add"), icon="person_add", on_click=_open_add
                ).props("color=primary")

            selection_bar()
            await payees_list()
