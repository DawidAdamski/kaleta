# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — Import tab (saved filename-pattern import rules)."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.schemas.import_rule import ImportRuleUpdate
from kaleta.services import AccountService, ImportRuleService, with_session
from kaleta.views.error_handling import notify_kaleta_error


def _column_summary(mapping: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("date", "amount", "description", "payee", "debit", "credit"):
        value = mapping.get(key)
        if value is not None and value != "":
            parts.append(f"{key}:{value}")
    return ", ".join(parts) if parts else "—"


async def render_import_tab() -> None:
    async def _load_accounts(session: Any) -> dict[int, str]:
        accounts = await AccountService(session).list()
        return {a.id: f"{a.name} ({a.currency})" for a in accounts}

    account_options = await with_session(_load_accounts)

    with ui.card().classes("p-6 w-full"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("rule", color="primary").classes("text-xl")
            ui.label(t("settings.import_rules_title")).classes("text-lg font-semibold")
        ui.label(t("settings.import_rules_hint")).classes("text-xs text-slate-500 mb-4")

        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[480px] gap-3"):
            dialog_title = ui.label(t("settings.import_rule_edit")).classes("text-lg font-bold")
            pattern_input = ui.input(t("import.filename_pattern")).classes("w-full")
            account_sel = ui.select(account_options, label=t("import.target_account")).classes(
                "w-full"
            )
            active_switch = ui.switch(t("settings.import_rule_active"), value=True)
            dialog_rule_id: dict[str, int | None] = {"value": None}

            async def _submit() -> None:
                pattern = (pattern_input.value or "").strip()
                if not pattern:
                    ui.notify(t("settings.import_rule_pattern_required"), type="negative")
                    return
                if not account_sel.value:
                    ui.notify(t("settings.import_rule_account_required"), type="negative")
                    return
                rule_id = dialog_rule_id["value"]
                if rule_id is None:
                    dialog.close()
                    return

                async def _save(session: Any) -> None:
                    await ImportRuleService(session).update(
                        rule_id,
                        ImportRuleUpdate(
                            filename_pattern=pattern,
                            account_id=int(account_sel.value),
                            is_active=bool(active_switch.value),
                        ),
                    )

                try:
                    await with_session(_save)
                except KaletaError as exc:
                    notify_kaleta_error(exc)
                    return
                ui.notify(t("settings.import_rule_updated"), type="positive")
                dialog.close()
                rules_grid.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-1"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.save"), on_click=_submit).props("color=primary")

        @ui.refreshable
        async def rules_grid() -> None:
            async def _load(session: Any) -> list[Any]:
                return await ImportRuleService(session).list()

            rules = await with_session(_load)
            if not rules:
                ui.label(t("settings.import_rules_empty")).classes("text-slate-400 text-sm")
                return

            cols = [
                {
                    "name": "pattern",
                    "label": t("import.filename_pattern"),
                    "field": "pattern",
                    "align": "left",
                },
                {
                    "name": "account",
                    "label": t("common.account"),
                    "field": "account",
                    "align": "left",
                },
                {
                    "name": "mapping",
                    "label": t("settings.import_rule_mapping"),
                    "field": "mapping",
                    "align": "left",
                },
                {
                    "name": "last_used",
                    "label": t("settings.import_rule_last_used"),
                    "field": "last_used",
                    "align": "left",
                },
                {
                    "name": "active",
                    "label": t("settings.import_rule_active"),
                    "field": "active",
                    "align": "center",
                },
                {"name": "actions", "label": "", "field": "id", "align": "right"},
            ]
            rows = [
                {
                    "id": rule.id,
                    "pattern": rule.filename_pattern,
                    "account": rule.account.name if rule.account else str(rule.account_id),
                    "mapping": _column_summary(dict(rule.column_mapping or {})),
                    "last_used": (
                        rule.last_used_at.date().isoformat() if rule.last_used_at else "—"
                    ),
                    "active": t("common.yes") if rule.is_active else t("common.no"),
                    "is_active": rule.is_active,
                    "account_id": rule.account_id,
                }
                for rule in rules
            ]
            table = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full")
            table.add_slot(
                "body-cell-actions",
                """
                <q-td :props="props">
                  <q-btn flat dense round icon="edit" size="sm"
                    @click="$parent.$emit('edit', props.row)" />
                  <q-btn flat dense round icon="toggle_on" size="sm"
                    @click="$parent.$emit('toggle', props.row)" />
                  <q-btn flat dense round icon="delete" size="sm" color="negative"
                    @click="$parent.$emit('delete', props.row)" />
                </q-td>
                """,
            )

            async def _edit(e: Any) -> None:
                row = e.args
                dialog_rule_id["value"] = int(row["id"])
                dialog_title.set_text(t("settings.import_rule_edit"))
                pattern_input.value = row["pattern"]
                account_sel.value = int(row["account_id"])
                active_switch.value = bool(row["is_active"])
                dialog.open()

            async def _toggle(e: Any) -> None:
                row = e.args
                rule_id = int(row["id"])
                new_active = not bool(row["is_active"])

                async def _save(session: Any) -> None:
                    await ImportRuleService(session).update(
                        rule_id,
                        ImportRuleUpdate(is_active=new_active),
                    )

                try:
                    await with_session(_save)
                except KaletaError as exc:
                    notify_kaleta_error(exc)
                    return
                ui.notify(
                    t(
                        "settings.import_rule_toggled",
                        state=t("common.yes") if new_active else t("common.no"),
                    ),
                    type="positive",
                )
                rules_grid.refresh()

            async def _delete(e: Any) -> None:
                row = e.args
                rule_id = int(row["id"])

                async def _drop(session: Any) -> None:
                    await ImportRuleService(session).delete(rule_id)

                await with_session(_drop)
                ui.notify(t("settings.import_rule_deleted"), type="positive")
                rules_grid.refresh()

            table.on("edit", _edit)
            table.on("toggle", _toggle)
            table.on("delete", _delete)

        await rules_grid()
