from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.models.institution import InstitutionType
from kaleta.schemas.institution import InstitutionCreate, InstitutionUpdate
from kaleta.services import InstitutionService
from kaleta.views.layout import page_layout

_TYPE_LABELS: dict[str, str] = {
    InstitutionType.BANK: "Bank",
    InstitutionType.FINTECH: "Fintech",
    InstitutionType.CREDIT_UNION: "Credit Union",
    InstitutionType.BROKER: "Broker",
    InstitutionType.INSURANCE: "Insurance",
    InstitutionType.OTHER: "Other",
}

_TYPE_ICONS: dict[str, str] = {
    InstitutionType.BANK: "account_balance",
    InstitutionType.FINTECH: "phone_iphone",
    InstitutionType.CREDIT_UNION: "groups",
    InstitutionType.BROKER: "show_chart",
    InstitutionType.INSURANCE: "health_and_safety",
    InstitutionType.OTHER: "business",
}


def register() -> None:
    @ui.page("/institutions")
    async def institutions_page() -> None:
        async with AsyncSessionFactory() as session:
            institution_list = await InstitutionService(session).list()

        selected_id: list[int | None] = [None]

        with page_layout("Institutions"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Institutions").classes("text-2xl font-bold")
                ui.button("Add Institution", icon="add", on_click=lambda: _open_add()).props(
                    "color=primary"
                )

            @ui.refreshable
            def institution_cards() -> None:
                if not institution_list:
                    ui.label("No institutions yet. Add one to get started.").classes(
                        "text-grey-6 mt-8"
                    )
                    return
                with ui.grid(columns=3).classes("w-full gap-4"):
                    for inst in institution_list:
                        color = inst.color or "#607d8b"
                        icon = _TYPE_ICONS.get(inst.type, "business")
                        with ui.card().classes("p-4 gap-2"):
                            with ui.row().classes("items-center gap-3 w-full"):
                                ui.icon(icon).style(f"color: {color}; font-size: 2rem;")
                                with ui.column().classes("gap-0 flex-1 min-w-0"):
                                    ui.label(inst.name).classes("font-bold text-base truncate")
                                    ui.label(_TYPE_LABELS.get(inst.type, inst.type)).classes(
                                        "text-xs text-grey-6"
                                    )
                            if inst.description:
                                ui.label(inst.description).classes(
                                    "text-sm text-grey-7 line-clamp-2"
                                )
                            if inst.website:
                                ui.label(inst.website).classes("text-xs text-blue-6 truncate")
                            with ui.row().classes("w-full justify-end gap-1 mt-1"):
                                ui.button(icon="edit", on_click=lambda i=inst: _open_edit(i)).props(
                                    "flat round dense color=primary size=sm"
                                )
                                ui.button(
                                    icon="delete", on_click=lambda i=inst: _open_delete(i)
                                ).props("flat round dense color=negative size=sm")

            institution_cards()

        # ── Add dialog ────────────────────────────────────────────────────────
        with ui.dialog() as add_dialog, ui.card().classes("w-[480px]"):
            ui.label("Add Institution").classes("text-lg font-bold mb-2")
            add_name = ui.input("Name *").classes("w-full")
            add_type = ui.select(
                {t.value: _TYPE_LABELS[t] for t in InstitutionType},
                label="Type",
                value=InstitutionType.BANK.value,
            ).classes("w-full")
            add_color = ui.input("Color (hex, e.g. #1976d2)", value="#607d8b").classes("w-full")
            add_website = ui.input("Website").classes("w-full")
            add_desc = ui.textarea("Description").classes("w-full").props("rows=2")

            async def save_add() -> None:
                if not add_name.value or not add_name.value.strip():
                    ui.notify("Name is required.", type="negative")
                    return
                data = InstitutionCreate(
                    name=add_name.value.strip(),
                    type=InstitutionType(add_type.value),
                    color=add_color.value.strip() or None,
                    website=add_website.value.strip() or None,
                    description=add_desc.value.strip() or None,
                )
                async with AsyncSessionFactory() as session:
                    inst = await InstitutionService(session).create(data)
                institution_list.append(inst)
                institution_cards.refresh()
                ui.notify("Institution created.", type="positive")
                add_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=add_dialog.close).props("flat")
                ui.button("Save", on_click=save_add).props("color=primary")

        # ── Edit dialog ───────────────────────────────────────────────────────
        with ui.dialog() as edit_dialog, ui.card().classes("w-[480px]"):
            ui.label("Edit Institution").classes("text-lg font-bold mb-2")
            edit_name = ui.input("Name *").classes("w-full")
            edit_type = ui.select(
                {t.value: _TYPE_LABELS[t] for t in InstitutionType},
                label="Type",
            ).classes("w-full")
            edit_color = ui.input("Color (hex, e.g. #1976d2)").classes("w-full")
            edit_website = ui.input("Website").classes("w-full")
            edit_desc = ui.textarea("Description").classes("w-full").props("rows=2")

            async def save_edit() -> None:
                iid = selected_id[0]
                if iid is None:
                    return
                if not edit_name.value or not edit_name.value.strip():
                    ui.notify("Name is required.", type="negative")
                    return
                data = InstitutionUpdate(
                    name=edit_name.value.strip(),
                    type=InstitutionType(edit_type.value),
                    color=edit_color.value.strip() or None,
                    website=edit_website.value.strip() or None,
                    description=edit_desc.value.strip() or None,
                )
                async with AsyncSessionFactory() as session:
                    updated = await InstitutionService(session).update(iid, data)
                if updated:
                    for idx, inst in enumerate(institution_list):
                        if inst.id == iid:
                            institution_list[idx] = updated
                            break
                institution_cards.refresh()
                ui.notify("Institution updated.", type="positive")
                edit_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=edit_dialog.close).props("flat")
                ui.button("Save", on_click=save_edit).props("color=primary")

        # ── Delete dialog ─────────────────────────────────────────────────────
        with ui.dialog() as delete_dialog, ui.card().classes("w-96"):
            delete_label = ui.label("").classes("text-base mb-4")

            async def confirm_delete() -> None:
                iid = selected_id[0]
                if iid is None:
                    return
                async with AsyncSessionFactory() as session:
                    await InstitutionService(session).delete(iid)
                for inst in institution_list:
                    if inst.id == iid:
                        institution_list.remove(inst)
                        break
                institution_cards.refresh()
                ui.notify("Institution deleted.", type="positive")
                delete_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancel", on_click=delete_dialog.close).props("flat")
                ui.button("Delete", on_click=confirm_delete).props("color=negative")

        def _open_add() -> None:
            add_name.set_value("")
            add_type.set_value(InstitutionType.BANK.value)
            add_color.set_value("#607d8b")
            add_website.set_value("")
            add_desc.set_value("")
            add_dialog.open()

        def _open_edit(inst: object) -> None:
            selected_id[0] = inst.id  # type: ignore[attr-defined]
            edit_name.set_value(inst.name)  # type: ignore[attr-defined]
            edit_type.set_value(inst.type.value)  # type: ignore[attr-defined]
            edit_color.set_value(inst.color or "")  # type: ignore[attr-defined]
            edit_website.set_value(inst.website or "")  # type: ignore[attr-defined]
            edit_desc.set_value(inst.description or "")  # type: ignore[attr-defined]
            edit_dialog.open()

        def _open_delete(inst: object) -> None:
            selected_id[0] = inst.id  # type: ignore[attr-defined]
            delete_label.set_text(  # type: ignore[attr-defined]
                f'Delete institution "{inst.name}"? Accounts linked to it will be unlinked.'  # type: ignore[attr-defined]
            )
            delete_dialog.open()
