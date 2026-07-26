# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.schemas.categorisation_rule import (
    CategorisationRuleCreate,
    CategorisationRuleResponse,
    CategorisationRuleUpdate,
    RuleMatchMode,
)
from kaleta.services import CategoryService, RuleService, with_session
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.layout import page_layout


def _to_response(rule: Any) -> CategorisationRuleResponse:
    return CategorisationRuleResponse(
        id=rule.id,
        pattern=rule.pattern,
        match_mode=rule.match_mode,
        category_id=rule.category_id,
        category_name=rule.category.name if rule.category else None,
        is_active=rule.is_active,
        priority=rule.priority,
    )


def register() -> None:
    @ui.page("/rules")
    async def rules_page() -> None:
        dialog_rule_id: dict[str, int | None] = {"value": None}

        async def _load_category_options() -> dict[int, str]:
            async def _load(session: Any) -> dict[int, str]:
                cats = await CategoryService(session).list()
                return {c.id: c.name for c in cats}

            return await with_session(_load)

        category_options = await _load_category_options()

        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[480px] gap-3"):
            dialog_title = ui.label("").classes("text-lg font-bold")
            pattern_input = (
                ui.input(t("rules.pattern"))
                .classes("w-full")
                .props(f'placeholder="{t("rules.pattern_hint")}"')
            )
            ui.label(t("rules.match_mode_contains")).classes("text-sm text-slate-500")
            category_sel = ui.select(
                category_options,
                label=t("common.category"),
            ).classes("w-full")
            active_switch = ui.switch(t("rules.active"), value=True)
            priority_input = ui.number(t("rules.priority"), value=0, step=1).classes("w-full")

            async def _submit() -> None:
                pattern = (pattern_input.value or "").strip()
                if not pattern:
                    ui.notify(t("rules.pattern_required"), type="negative")
                    return
                if not category_sel.value:
                    ui.notify(t("rules.category_required"), type="negative")
                    return
                payload = CategorisationRuleCreate(
                    pattern=pattern,
                    category_id=int(category_sel.value),
                    match_mode=RuleMatchMode.CONTAINS,
                    is_active=bool(active_switch.value),
                    priority=int(priority_input.value or 0),
                )

                async def _save(session: Any) -> None:
                    svc = RuleService(session)
                    if dialog_rule_id["value"] is None:
                        await svc.create(payload)
                        ui.notify(t("rules.created"), type="positive")
                    else:
                        await svc.update(
                            dialog_rule_id["value"],
                            CategorisationRuleUpdate(**payload.model_dump()),
                        )
                        ui.notify(t("rules.updated"), type="positive")

                try:
                    await with_session(_save)
                except KaletaError as exc:
                    notify_kaleta_error(exc)
                    return
                dialog.close()
                rules_grid.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-1"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.save"), on_click=_submit).props("color=primary")

        delete_id: dict[str, int | None] = {"value": None}
        delete_dialog = ui.dialog()
        with delete_dialog, ui.card().classes("w-[360px]"):
            delete_label = ui.label("").classes("text-base")
            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")

                async def _do_delete() -> None:
                    rid = delete_id["value"]
                    if rid is not None:

                        async def _delete(session: Any) -> None:
                            await RuleService(session).delete(rid)

                        await with_session(_delete)
                    ui.notify(t("rules.deleted"), type="positive")
                    delete_dialog.close()
                    rules_grid.refresh()

                ui.button(t("common.delete"), icon="delete", on_click=_do_delete).props(
                    "color=negative"
                )

        def _open_add() -> None:
            dialog_rule_id["value"] = None
            dialog_title.set_text(t("rules.add"))
            pattern_input.set_value("")
            category_sel.set_value(None)
            active_switch.set_value(True)
            priority_input.set_value(0)
            dialog.open()

        def _open_edit(rule: CategorisationRuleResponse) -> None:
            dialog_rule_id["value"] = rule.id
            dialog_title.set_text(t("rules.edit"))
            pattern_input.set_value(rule.pattern)
            category_sel.set_value(rule.category_id)
            active_switch.set_value(rule.is_active)
            priority_input.set_value(rule.priority)
            dialog.open()

        def _open_delete(rule: CategorisationRuleResponse) -> None:
            delete_id["value"] = rule.id
            delete_label.set_text(
                t("rules.delete_confirm", pattern=rule.pattern, category=rule.category_name or "")
            )
            delete_dialog.open()

        @ui.refreshable
        async def rules_grid() -> None:
            async def _load(session: Any) -> list[CategorisationRuleResponse]:
                rules = await RuleService(session).list()
                return [_to_response(rule) for rule in rules]

            rules = await with_session(_load)

            if not rules:
                with ui.column().classes("w-full items-center py-20 gap-3 text-slate-400"):
                    ui.icon("rule", size="4rem")
                    ui.label(t("rules.no_rules")).classes("text-lg")
                    ui.label(t("rules.no_rules_hint")).classes("text-sm")
                return

            tbl = (
                ui.table(
                    columns=[
                        {
                            "name": "pattern",
                            "label": t("rules.pattern"),
                            "field": "pattern",
                            "align": "left",
                        },
                        {
                            "name": "category_name",
                            "label": t("common.category"),
                            "field": "category_name",
                            "align": "left",
                        },
                        {
                            "name": "match",
                            "label": t("rules.match_mode"),
                            "field": "match",
                            "align": "left",
                        },
                        {
                            "name": "is_active",
                            "label": t("rules.active"),
                            "field": "is_active",
                            "align": "left",
                        },
                        {
                            "name": "priority",
                            "label": t("rules.priority"),
                            "field": "priority",
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
                            "id": r.id,
                            "pattern": r.pattern,
                            "category_name": r.category_name or "—",
                            "match": t("rules.match_mode_contains"),
                            "is_active": t("common.yes") if r.is_active else t("common.no"),
                            "priority": r.priority,
                        }
                        for r in rules
                    ],
                    row_key="id",
                )
                .classes("w-full")
                .props("flat bordered")
            )
            tbl.add_slot(
                "body-cell-actions",
                '<q-td :props="props" auto-width>'
                '<q-btn flat round dense icon="edit" color="primary" size="sm"'
                " @click=\"$parent.$emit('edit_rule', props.row.id)\" />"
                '<q-btn flat round dense icon="delete" color="negative" size="sm"'
                " @click=\"$parent.$emit('delete_rule', props.row.id)\" />"
                "</q-td>",
            )

            def _on_edit(e: object) -> None:
                rid = e.args  # type: ignore[attr-defined]
                rule = next((r for r in rules if r.id == rid), None)
                if rule:
                    _open_edit(rule)

            def _on_delete(e: object) -> None:
                rid = e.args  # type: ignore[attr-defined]
                rule = next((r for r in rules if r.id == rid), None)
                if rule:
                    _open_delete(rule)

            tbl.on("edit_rule", _on_edit)
            tbl.on("delete_rule", _on_delete)

        with page_layout(t("rules.title")):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-1"):
                    ui.label(t("rules.title")).classes("text-2xl font-bold")
                    ui.label(t("rules.subtitle")).classes("text-sm text-slate-500")
                ui.button(t("rules.add"), icon="add", on_click=_open_add).props("color=primary")

            await rules_grid()
