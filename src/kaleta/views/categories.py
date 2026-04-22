from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.category import Category, CategoryType
from kaleta.schemas.category import CategoryCreate, CategoryUpdate
from kaleta.services import CategoryService
from kaleta.services.category_service import TemplatePreview
from kaleta.views.layout import page_layout
from kaleta.views.theme import BODY_MUTED, DIALOG_TITLE, PAGE_TITLE, SECTION_CARD


def register() -> None:
    @ui.page("/categories")
    async def categories_page() -> None:

        edit_state: dict[str, int | None] = {"id": None}
        delete_state: dict[str, int | None] = {"id": None}

        # ── Add dialog ────────────────────────────────────────────────────
        with ui.dialog() as add_dialog, ui.card().classes("w-96"):
            ui.label(t("categories.add")).classes(f"{DIALOG_TITLE} mb-2")
            add_name = ui.input(f"{t('common.name')} *").classes("w-full")
            add_type = ui.select(
                {
                    CategoryType.EXPENSE.value: t("common.expense"),
                    CategoryType.INCOME.value: t("common.income"),
                },
                label=t("common.type"),
                value=CategoryType.EXPENSE.value,
            ).classes("w-full")
            add_parent = ui.select(
                {0: t("categories.none_parent")}, label=t("categories.parent"), value=0
            ).classes("w-full")

            async def _load_add_parents(cat_type: str) -> None:
                async with AsyncSessionFactory() as session:
                    roots = await CategoryService(session).list_roots(type=CategoryType(cat_type))
                options: dict[int, str] = {0: t("categories.none_parent")}
                options.update({c.id: c.name for c in roots})
                add_parent.set_options(options, value=0)

            add_type.on_value_change(lambda e: _load_add_parents(e.value))

            async def save_add() -> None:
                if not add_name.value.strip():
                    ui.notify(t("categories.name_required"), type="negative")
                    return
                parent_id = add_parent.value if add_parent.value != 0 else None
                data = CategoryCreate(
                    name=add_name.value.strip(),
                    type=CategoryType(add_type.value),
                    parent_id=parent_id,
                )
                async with AsyncSessionFactory() as session:
                    await CategoryService(session).create(data)
                ui.notify(t("categories.created"), type="positive")
                add_name.set_value("")
                add_parent.set_value(0)
                add_dialog.close()
                category_list.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=add_dialog.close).props("flat")
                ui.button(t("common.save"), on_click=save_add).props("color=primary")
            ui.keyboard(
                on_key=lambda e: (
                    save_add()
                    if e.key == "Enter" and e.action.keydown
                    else add_dialog.close()
                    if e.key == "Escape" and e.action.keydown
                    else None
                )
            )

        async def open_add_dialog(
            preset_type: CategoryType = CategoryType.EXPENSE,
            preset_parent_id: int | None = None,
            preset_parent_name: str = "",
        ) -> None:
            add_name.set_value("")
            add_type.set_value(preset_type.value)
            await _load_add_parents(preset_type.value)
            add_parent.set_value(preset_parent_id or 0)
            add_dialog.open()

        # ── Edit dialog ───────────────────────────────────────────────────
        with ui.dialog() as edit_dialog, ui.card().classes("w-96"):
            ui.label(t("categories.edit")).classes(f"{DIALOG_TITLE} mb-2")
            edit_name = ui.input(f"{t('common.name')} *").classes("w-full")
            edit_type = ui.select(
                {
                    CategoryType.EXPENSE.value: t("common.expense"),
                    CategoryType.INCOME.value: t("common.income"),
                },
                label=t("common.type"),
            ).classes("w-full")
            edit_parent = ui.select(
                {0: t("categories.none_parent")}, label=t("categories.parent"), value=0
            ).classes("w-full")

            async def save_edit() -> None:
                category_id = edit_state["id"]
                if category_id is None:
                    return
                if not edit_name.value.strip():
                    ui.notify(t("categories.name_required"), type="negative")
                    return
                parent_id = edit_parent.value if edit_parent.value != 0 else None
                data = CategoryUpdate(
                    name=edit_name.value.strip(),
                    type=CategoryType(edit_type.value),
                    parent_id=parent_id,
                )
                async with AsyncSessionFactory() as session:
                    await CategoryService(session).update(category_id, data)
                ui.notify(t("categories.updated"), type="positive")
                edit_dialog.close()
                category_list.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=edit_dialog.close).props("flat")
                ui.button(t("common.save"), on_click=save_edit).props("color=primary")
            ui.keyboard(
                on_key=lambda e: (
                    save_edit()
                    if e.key == "Enter" and e.action.keydown
                    else edit_dialog.close()
                    if e.key == "Escape" and e.action.keydown
                    else None
                )
            )

        async def open_edit_dialog(
            cat: Category, cat_type: CategoryType, parent_id: int | None
        ) -> None:
            edit_state["id"] = cat.id
            edit_name.set_value(cat.name)
            edit_type.set_value(cat_type.value)
            async with AsyncSessionFactory() as session:
                roots = await CategoryService(session).list_roots(type=cat_type)
            options: dict[int, str] = {0: t("categories.none_parent")}
            options.update({c.id: c.name for c in roots if c.id != cat.id})
            edit_parent.set_options(options, value=parent_id or 0)
            edit_dialog.open()

        # ── Delete dialog ─────────────────────────────────────────────────
        with ui.dialog() as delete_dialog, ui.card().classes("w-80"):
            ui.label(t("common.delete")).classes(f"{DIALOG_TITLE} mb-2")
            delete_label = ui.label("").classes("text-sm mb-4")

            async def confirm_delete() -> None:
                category_id = delete_state["id"]
                if category_id is None:
                    return
                async with AsyncSessionFactory() as session:
                    await CategoryService(session).delete(category_id)
                ui.notify(t("categories.deleted"), type="positive")
                delete_dialog.close()
                category_list.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")
                ui.button(t("common.delete"), on_click=confirm_delete).props("color=negative")

        def open_delete_dialog(cat: Category, has_children: bool) -> None:
            delete_state["id"] = cat.id
            suffix = f" {t('categories.delete_subcategory_warning')}" if has_children else ""
            delete_label.set_text(f"{t('categories.delete_confirm', name=cat.name)}{suffix}")
            delete_dialog.open()

        # ── Refreshable tree list ─────────────────────────────────────────
        @ui.refreshable
        async def category_list() -> None:
            async with AsyncSessionFactory() as session:
                svc = CategoryService(session)
                income_roots = await svc.list_roots(type=CategoryType.INCOME)
                expense_roots = await svc.list_roots(type=CategoryType.EXPENSE)

            def _render_group(roots: list[Category], group_type: CategoryType) -> None:
                total = sum(1 + len(r.children) for r in roots)
                is_income = group_type == CategoryType.INCOME
                color = "green" if is_income else "red"
                icon = "trending_up" if is_income else "trending_down"
                label = t("categories.income_type") if is_income else t("categories.expense")

                with ui.card().classes(f"{SECTION_CARD} p-0 overflow-hidden"):
                    # Header row
                    with ui.row().classes("items-center gap-2 px-4 py-3 border-b"):
                        ui.icon(icon, color=color).classes("text-xl")
                        ui.label(label).classes("text-lg font-semibold text-primary flex-1")
                        ui.badge(str(total), color=color)
                        ui.button(
                            icon="add",
                            on_click=lambda gt=group_type: open_add_dialog(gt),
                        ).props("flat round dense color=primary size=sm").tooltip(
                            t("categories.add_type_category", type=label)
                        )

                    if not roots:
                        ui.label(t("categories.no_categories")).classes(f"{BODY_MUTED} px-4 py-3")
                        return

                    # Tree rows
                    with ui.column().classes("w-full gap-0"):
                        for parent in sorted(roots, key=lambda c: c.name):
                            # Parent row
                            with ui.row().classes(
                                "k-cat-row items-center w-full px-4 py-2 gap-2"
                                " hover:bg-slate-50 border-b border-slate-200"
                            ):
                                ui.icon("folder_open").classes("text-primary/70")
                                ui.label(parent.name).classes("flex-1 font-medium")
                                if not parent.children:
                                    # Only show "add child" on parents without children limit
                                    pass
                                ui.button(
                                    icon="add_circle_outline",
                                    on_click=lambda p=parent, gt=group_type: open_add_dialog(
                                        gt, p.id, p.name
                                    ),
                                ).props("flat round dense size=sm color=grey-6").tooltip(
                                    t("categories.add_subcategory")
                                )
                                ui.button(
                                    icon="edit",
                                    on_click=lambda c=parent, gt=group_type: open_edit_dialog(
                                        c, gt, c.parent_id
                                    ),
                                ).props("flat round dense size=sm color=primary")
                                ui.button(
                                    icon="delete",
                                    on_click=lambda c=parent: open_delete_dialog(
                                        c, bool(c.children)
                                    ),
                                ).props("flat round dense size=sm color=negative")

                            # Child rows
                            for child in sorted(parent.children, key=lambda c: c.name):
                                with ui.row().classes(
                                    "k-cat-row items-center w-full pl-10 pr-4 py-1 gap-2"
                                    " hover:bg-slate-50 border-b border-slate-200"
                                ):
                                    ui.icon("subdirectory_arrow_right").classes(
                                        "text-slate-400 text-sm"
                                    )
                                    ui.label(child.name).classes(
                                        "k-subcat-label flex-1 text-slate-700"
                                    )
                                    ui.button(
                                        icon="edit",
                                        on_click=lambda c=child, gt=group_type: open_edit_dialog(
                                            c, gt, c.parent_id
                                        ),
                                    ).props("flat round dense size=sm color=primary")
                                    ui.button(
                                        icon="delete",
                                        on_click=lambda c=child: open_delete_dialog(c, False),
                                    ).props("flat round dense size=sm color=negative")

            _render_group(income_roots, CategoryType.INCOME)
            _render_group(expense_roots, CategoryType.EXPENSE)

        # ── Template picker + preview ─────────────────────────────────────
        template_state: dict[str, TemplatePreview | None] = {"preview": None}

        with ui.dialog() as template_preview_dialog, ui.card().classes("w-[460px]"):
            preview_title = ui.label("").classes(f"{DIALOG_TITLE} mb-2")
            preview_summary = ui.label("").classes("text-sm mb-3")
            preview_list = ui.column().classes("gap-0 max-h-64 overflow-auto w-full")
            preview_skipped = ui.label("").classes(f"{BODY_MUTED} text-xs mt-2")

            async def _apply_preview() -> None:
                preview = template_state["preview"]
                if preview is None:
                    return
                async with AsyncSessionFactory() as session:
                    created = await CategoryService(session).apply_template(preview.key)
                ui.notify(
                    t("categories.template_applied", count=created),
                    type="positive",
                )
                template_preview_dialog.close()
                category_list.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=template_preview_dialog.close).props("flat")
                apply_btn = ui.button(
                    t("categories.template_apply"), on_click=_apply_preview
                ).props("color=primary")

        def _render_preview(preview: TemplatePreview) -> None:
            template_state["preview"] = preview
            name = t(f"categories.template_name_{preview.key}")
            preview_title.set_text(t("categories.template_preview_title", name=name))
            if preview.total_to_add == 0:
                preview_summary.set_text(t("categories.template_nothing_to_add"))
                apply_btn.props("disable")
            else:
                preview_summary.set_text(
                    t("categories.template_will_add", count=preview.total_to_add)
                )
                apply_btn.props(remove="disable")
            preview_list.clear()
            with preview_list:
                for name in preview.to_add_income:
                    with ui.row().classes("items-center gap-2 py-1"):
                        ui.icon("trending_up", color="green").classes("text-sm")
                        ui.label(name).classes("text-sm")
                for name in preview.to_add_expense:
                    with ui.row().classes("items-center gap-2 py-1"):
                        ui.icon("trending_down", color="red").classes("text-sm")
                        ui.label(name).classes("text-sm")
            skipped_all = preview.skipped_income + preview.skipped_expense
            if skipped_all:
                preview_skipped.set_text(
                    t("categories.template_skipped", names=", ".join(skipped_all))
                )
            else:
                preview_skipped.set_text("")

        async def _open_template_preview(key: str) -> None:
            async with AsyncSessionFactory() as session:
                preview = await CategoryService(session).preview_template(key)
            _render_preview(preview)
            template_preview_dialog.open()

        with ui.dialog() as template_picker_dialog, ui.card().classes("w-[420px]"):
            ui.label(t("categories.template_picker_title")).classes(f"{DIALOG_TITLE} mb-2")
            with ui.column().classes("gap-2 w-full"):
                for tmpl_key in CategoryService.list_templates():

                    async def _pick(k: str = tmpl_key) -> None:
                        template_picker_dialog.close()
                        await _open_template_preview(k)

                    with ui.card().classes(
                        "w-full cursor-pointer hover:bg-slate-50 p-3 border"
                    ).on("click", _pick):
                        ui.label(t(f"categories.template_name_{tmpl_key}")).classes(
                            "font-medium text-primary"
                        )
                        ui.label(t(f"categories.template_desc_{tmpl_key}")).classes(
                            f"{BODY_MUTED} text-xs"
                        )
            with ui.row().classes("w-full justify-end mt-3"):
                ui.button(t("common.cancel"), on_click=template_picker_dialog.close).props("flat")

        # ── Page layout ───────────────────────────────────────────────────
        with page_layout(t("categories.title")):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("categories.title")).classes(PAGE_TITLE)
                with ui.row().classes("gap-2"):
                    ui.button(
                        t("categories.load_template"),
                        icon="library_add",
                        on_click=template_picker_dialog.open,
                    ).props("outline color=primary")
                    ui.button(
                        t("categories.add"), icon="add", on_click=lambda: open_add_dialog()
                    ).props("color=primary")

            await category_list()
