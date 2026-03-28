from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.institution import InstitutionType
from kaleta.schemas.institution import InstitutionCreate, InstitutionUpdate
from kaleta.services import InstitutionService
from kaleta.views.layout import page_layout

_TYPE_ICONS: dict[str, str] = {
    InstitutionType.BANK: "account_balance",
    InstitutionType.FINTECH: "phone_iphone",
    InstitutionType.CREDIT_UNION: "groups",
    InstitutionType.BROKER: "show_chart",
    InstitutionType.INSURANCE: "health_and_safety",
    InstitutionType.OTHER: "business",
}


def _type_labels() -> dict[str, str]:
    return {
        InstitutionType.BANK: t("institutions.bank"),
        InstitutionType.FINTECH: t("institutions.fintech"),
        InstitutionType.CREDIT_UNION: t("institutions.credit_union"),
        InstitutionType.BROKER: t("institutions.broker"),
        InstitutionType.INSURANCE: t("institutions.insurance"),
        InstitutionType.OTHER: t("institutions.other"),
    }


def register() -> None:
    @ui.page("/institutions")
    async def institutions_page() -> None:
        async with AsyncSessionFactory() as session:
            institution_list = await InstitutionService(session).list()

        selected_id: list[int | None] = [None]

        with page_layout(t("institutions.title")):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("institutions.title")).classes("text-2xl font-bold")
                ui.button(
                    t("institutions.add"), icon="add", on_click=lambda: _open_add()
                ).props("color=primary")

            @ui.refreshable
            def institution_cards() -> None:
                labels = _type_labels()
                if not institution_list:
                    ui.label(t("institutions.no_institutions")).classes("text-grey-6 mt-8")
                    return
                with ui.grid(columns=3).classes("w-full gap-4"):
                    for inst in institution_list:
                        color = inst.color or "#1976d2"
                        icon = _TYPE_ICONS.get(inst.type, "business")
                        with ui.card().classes("p-4 gap-2"):
                            with ui.row().classes("items-center gap-3 w-full"):
                                ui.icon(icon).style(f"color: {color}; font-size: 2rem;")
                                with ui.column().classes("gap-0 flex-1 min-w-0"):
                                    ui.label(inst.name).classes("font-bold text-base truncate")
                                    ui.label(labels.get(inst.type, inst.type)).classes(
                                        "text-xs text-grey-6"
                                    )
                            if inst.description:
                                ui.label(inst.description).classes(
                                    "text-sm text-grey-7 line-clamp-2"
                                )
                            if inst.website:
                                ui.label(inst.website).classes("text-xs text-blue-6 truncate")
                            with ui.row().classes("w-full justify-end gap-1 mt-1"):
                                ui.button(
                                    icon="edit", on_click=lambda i=inst: _open_edit(i)
                                ).props("flat round dense color=primary size=sm")
                                ui.button(
                                    icon="delete", on_click=lambda i=inst: _open_delete(i)
                                ).props("flat round dense color=negative size=sm")

            institution_cards()

        _swatch_style = (  # noqa: N806
            "width:36px;height:36px;border-radius:6px;"
            "border:1px solid rgba(0,0,0,0.2);flex-shrink:0;background:{}"
        )

        # ── Add dialog ────────────────────────────────────────────────────────
        with ui.dialog() as add_dialog, ui.card().classes("w-[480px]"):
            ui.label(t("institutions.add")).classes("text-lg font-bold mb-2")
            add_name = ui.input(f"{t('common.name')} *").classes("w-full")
            add_type = ui.select(
                {it.value: _type_labels()[it] for it in InstitutionType},
                label=t("common.type"),
                value=InstitutionType.BANK.value,
            ).classes("w-full")

            with ui.row().classes("items-center gap-2 w-full"):
                add_swatch = ui.element("div").style(_swatch_style.format("#1976d2"))
                add_color = ui.input(t("institutions.color"), value="#1976d2").classes("flex-1")

                def _add_sync_swatch() -> None:
                    add_swatch.style(_swatch_style.format(add_color.value or "#1976d2"))

                add_color.on_value_change(lambda _: _add_sync_swatch())

                with ui.button(icon="colorize").props("flat round dense").tooltip(
                    t("institutions.pick_color")
                ):
                    ui.color_picker(
                        on_pick=lambda e: (
                            add_color.set_value(e.color),
                            _add_sync_swatch(),
                        )
                    )

            add_website = ui.input(t("institutions.website")).classes("w-full")
            add_desc = ui.textarea(t("common.description")).classes("w-full").props("rows=2")

            async def save_add() -> None:
                if not add_name.value or not add_name.value.strip():
                    ui.notify(t("institutions.name_required"), type="negative")
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
                ui.notify(t("institutions.created"), type="positive")
                add_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=add_dialog.close).props("flat")
                ui.button(t("common.save"), on_click=save_add).props("color=primary")
            ui.keyboard(on_key=lambda e: (
                save_add() if e.key == "Enter" and e.action.keydown else
                add_dialog.close() if e.key == "Escape" and e.action.keydown else None
            ))

        # ── Edit dialog ───────────────────────────────────────────────────────
        with ui.dialog() as edit_dialog, ui.card().classes("w-[480px]"):
            ui.label(t("institutions.edit")).classes("text-lg font-bold mb-2")
            edit_name = ui.input(f"{t('common.name')} *").classes("w-full")
            edit_type = ui.select(
                {it.value: _type_labels()[it] for it in InstitutionType},
                label=t("common.type"),
            ).classes("w-full")

            with ui.row().classes("items-center gap-2 w-full"):
                edit_swatch = ui.element("div").style(_swatch_style.format("#1976d2"))
                edit_color = ui.input(t("institutions.color"), value="#1976d2").classes("flex-1")

                def _edit_sync_swatch() -> None:
                    edit_swatch.style(_swatch_style.format(edit_color.value or "#1976d2"))

                edit_color.on_value_change(lambda _: _edit_sync_swatch())

                with ui.button(icon="colorize").props("flat round dense").tooltip(
                    t("institutions.pick_color")
                ):
                    ui.color_picker(
                        on_pick=lambda e: (
                            edit_color.set_value(e.color),
                            _edit_sync_swatch(),
                        )
                    )

            edit_website = ui.input(t("institutions.website")).classes("w-full")
            edit_desc = ui.textarea(t("common.description")).classes("w-full").props("rows=2")

            async def save_edit() -> None:
                iid = selected_id[0]
                if iid is None:
                    return
                if not edit_name.value or not edit_name.value.strip():
                    ui.notify(t("institutions.name_required"), type="negative")
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
                ui.notify(t("institutions.updated"), type="positive")
                edit_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=edit_dialog.close).props("flat")
                ui.button(t("common.save"), on_click=save_edit).props("color=primary")
            ui.keyboard(on_key=lambda e: (
                save_edit() if e.key == "Enter" and e.action.keydown else
                edit_dialog.close() if e.key == "Escape" and e.action.keydown else None
            ))

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
                ui.notify(t("institutions.deleted"), type="positive")
                delete_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")
                ui.button(t("common.delete"), on_click=confirm_delete).props("color=negative")

        def _open_add() -> None:
            add_name.set_value("")
            add_type.set_value(InstitutionType.BANK.value)
            add_color.set_value("#1976d2")
            _add_sync_swatch()
            add_website.set_value("")
            add_desc.set_value("")
            add_dialog.open()

        def _open_edit(inst: object) -> None:
            selected_id[0] = inst.id  # type: ignore[attr-defined]
            edit_name.set_value(inst.name)  # type: ignore[attr-defined]
            edit_type.set_value(inst.type.value)  # type: ignore[attr-defined]
            edit_color.set_value(inst.color or "#1976d2")  # type: ignore[attr-defined]
            edit_website.set_value(inst.website or "")  # type: ignore[attr-defined]
            edit_desc.set_value(inst.description or "")  # type: ignore[attr-defined]
            _edit_sync_swatch()
            edit_dialog.open()

        def _open_delete(inst: object) -> None:
            selected_id[0] = inst.id  # type: ignore[attr-defined]
            delete_label.set_text(
                t("institutions.delete_confirm", name=inst.name)  # type: ignore[attr-defined]
            )
            delete_dialog.open()
