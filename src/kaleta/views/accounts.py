from __future__ import annotations

from collections import defaultdict

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.models.account import Account, AccountType
from kaleta.models.institution import Institution
from kaleta.schemas.account import AccountCreate, AccountUpdate
from kaleta.services import AccountService, InstitutionService
from kaleta.views.layout import page_layout

_TYPE_LABELS: dict[str, str] = {
    AccountType.CHECKING: "Checking",
    AccountType.SAVINGS: "Savings",
    AccountType.CASH: "Cash",
    AccountType.CREDIT: "Credit",
}

_TYPE_ICONS: dict[str, str] = {
    AccountType.CHECKING: "account_balance_wallet",
    AccountType.SAVINGS: "savings",
    AccountType.CASH: "payments",
    AccountType.CREDIT: "credit_card",
}

_COL_TYPE = {"name": "type", "label": "Type", "field": "type", "align": "left", "sortable": True}
_COL_INST = {
    "name": "institution",
    "label": "Institution",
    "field": "institution_name",
    "align": "left",
    "sortable": True,
}
_COL_NAME = {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True}
_COL_BAL = {
    "name": "balance",
    "label": "Balance (PLN)",
    "field": "balance",
    "align": "right",
    "sortable": True,
}
_COL_ACTIONS = {"name": "actions", "label": "", "field": "actions", "align": "right"}


def _columns_for(by: str) -> list[dict]:
    extra = _COL_INST if by == "type" else _COL_TYPE
    return [_COL_NAME, extra, _COL_BAL, _COL_ACTIONS]


def _account_row(a: Account) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "type": _TYPE_LABELS.get(a.type, a.type.value),
        "balance": f"{a.balance:,.2f}",
        "institution_id": a.institution_id,
        "institution_name": a.institution.name if a.institution else "",
    }


def register() -> None:
    @ui.page("/accounts")
    async def accounts_page() -> None:
        async with AsyncSessionFactory() as session:
            account_list: list[Account] = await AccountService(session).list()
            institution_list: list[Institution] = await InstitutionService(session).list()

        # group_by: "type" | "institution"
        group_by: list[str] = ["type"]
        selected_id: list[int | None] = [None]

        inst_options: dict[str | int, str] = {0: "— None —"}
        inst_options.update({i.id: i.name for i in institution_list})

        with page_layout("Accounts"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Accounts").classes("text-2xl font-bold")
                with ui.row().classes("gap-2 items-center"):
                    ui.label("Group by:").classes("text-sm text-grey-6")
                    group_toggle = ui.toggle(
                        {"type": "Type", "institution": "Institution"},
                        value="type",
                    ).props("dense")
                    ui.button("Add Account", icon="add", on_click=lambda: _open_add()).props(
                        "color=primary"
                    )

            @ui.refreshable
            def account_table() -> None:
                by = group_by[0]

                if by == "institution":
                    # group by institution (None → "No Institution")
                    groups: dict[str, list[Account]] = defaultdict(list)
                    inst_by_id: dict[int, str] = {i.id: i.name for i in institution_list}
                    for a in account_list:
                        key = inst_by_id.get(a.institution_id or -1, "No Institution")  # type: ignore[arg-type]
                        groups[key].append(a)
                else:
                    # group by account type
                    groups = defaultdict(list)
                    for a in account_list:
                        groups[_TYPE_LABELS.get(a.type, a.type.value)].append(a)

                if not groups:
                    ui.label("No accounts yet.").classes("text-grey-6 mt-8")
                    return

                for group_name in sorted(groups.keys()):
                    accts = groups[group_name]
                    with (
                        ui.expansion(group_name, icon=_group_icon(by, group_name, accts))
                        .classes("w-full border rounded-lg mb-2")
                        .props("default-opened")
                    ):
                        rows = [_account_row(a) for a in accts]
                        table = ui.table(columns=_columns_for(by), rows=rows, row_key="id").classes(
                            "w-full"
                        )
                        table.add_slot(
                            "body-cell-actions",
                            """
                            <q-td :props="props" class="text-right">
                              <q-btn flat round dense icon="edit" size="sm" color="primary"
                                     @click="$emit('edit', props.row)" />
                              <q-btn flat round dense icon="delete" size="sm" color="negative"
                                     @click="$emit('delete', props.row)" />
                            </q-td>
                            """,
                        )
                        table.on("edit", lambda e: _open_edit_row(e.args))
                        table.on("delete", lambda e: _open_delete_row(e.args))

            def _group_icon(by: str, name: str, accts: list[Account]) -> str:
                if by == "type":
                    rev = {v: k for k, v in _TYPE_LABELS.items()}
                    atype = rev.get(name)
                    return _TYPE_ICONS.get(atype, "folder") if atype else "folder"
                return "account_balance" if name != "No Institution" else "folder_off"

            def _on_group_change(e: object) -> None:
                group_by[0] = group_toggle.value  # type: ignore[attr-defined]
                account_table.refresh()

            group_toggle.on_value_change(_on_group_change)
            account_table()

        # ── Add dialog ────────────────────────────────────────────────────────
        with ui.dialog() as add_dialog, ui.card().classes("w-[420px]"):
            ui.label("Add Account").classes("text-lg font-bold mb-2")
            add_name = ui.input("Name *").classes("w-full")
            add_type = ui.select(
                {t.value: _TYPE_LABELS[t] for t in AccountType},
                label="Type",
                value=AccountType.CHECKING.value,
            ).classes("w-full")
            add_balance = ui.number("Initial Balance", value=0, format="%.2f").classes("w-full")
            add_inst = ui.select(inst_options, label="Institution", value=0).classes("w-full")

            async def save_add() -> None:
                if not add_name.value or not add_name.value.strip():
                    ui.notify("Name is required.", type="negative")
                    return
                inst_id = add_inst.value if add_inst.value != 0 else None
                data = AccountCreate(
                    name=add_name.value.strip(),
                    type=AccountType(add_type.value),
                    balance=add_balance.value,
                    institution_id=inst_id,
                )
                async with AsyncSessionFactory() as session:
                    acc = await AccountService(session).create(data)
                    # reload with institution relationship
                    acc = await AccountService(session).get(acc.id)
                if acc:
                    account_list.append(acc)
                account_table.refresh()
                ui.notify("Account created.", type="positive")
                add_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=add_dialog.close).props("flat")
                ui.button("Save", on_click=save_add).props("color=primary")

        # ── Edit dialog ───────────────────────────────────────────────────────
        with ui.dialog() as edit_dialog, ui.card().classes("w-[420px]"):
            ui.label("Edit Account").classes("text-lg font-bold mb-2")
            edit_name = ui.input("Name *").classes("w-full")
            edit_type = ui.select(
                {t.value: _TYPE_LABELS[t] for t in AccountType},
                label="Type",
            ).classes("w-full")
            edit_inst = ui.select(inst_options, label="Institution", value=0).classes("w-full")

            async def save_edit() -> None:
                aid = selected_id[0]
                if aid is None:
                    return
                if not edit_name.value or not edit_name.value.strip():
                    ui.notify("Name is required.", type="negative")
                    return
                inst_id = edit_inst.value if edit_inst.value != 0 else None
                data = AccountUpdate(
                    name=edit_name.value.strip(),
                    type=AccountType(edit_type.value),
                    institution_id=inst_id,
                )
                async with AsyncSessionFactory() as session:
                    updated = await AccountService(session).update(aid, data)
                    if updated:
                        updated = await AccountService(session).get(aid)
                if updated:
                    for idx, a in enumerate(account_list):
                        if a.id == aid:
                            account_list[idx] = updated
                            break
                account_table.refresh()
                ui.notify("Account updated.", type="positive")
                edit_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=edit_dialog.close).props("flat")
                ui.button("Save", on_click=save_edit).props("color=primary")

        # ── Delete dialog ─────────────────────────────────────────────────────
        with ui.dialog() as delete_dialog, ui.card().classes("w-96"):
            delete_label = ui.label("").classes("text-base mb-4")

            async def confirm_delete() -> None:
                aid = selected_id[0]
                if aid is None:
                    return
                async with AsyncSessionFactory() as session:
                    await AccountService(session).delete(aid)
                for a in account_list:
                    if a.id == aid:
                        account_list.remove(a)
                        break
                account_table.refresh()
                ui.notify("Account deleted.", type="positive")
                delete_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancel", on_click=delete_dialog.close).props("flat")
                ui.button("Delete", on_click=confirm_delete).props("color=negative")

        def _open_add() -> None:
            add_name.set_value("")
            add_type.set_value(AccountType.CHECKING.value)
            add_balance.set_value(0)
            add_inst.set_value(0)
            add_dialog.open()

        def _open_edit_row(row: dict) -> None:
            selected_id[0] = row["id"]
            edit_name.set_value(row["name"])
            rev = {v: k for k, v in _TYPE_LABELS.items()}
            atype = rev.get(row["type"])
            edit_type.set_value(atype.value if atype else AccountType.CHECKING.value)
            inst_id = row.get("institution_id") or 0
            edit_inst.set_value(inst_id)
            edit_dialog.open()

        def _open_delete_row(row: dict) -> None:
            selected_id[0] = row["id"]
            delete_label.set_text(
                f'Delete account "{row["name"]}"? All its transactions will be deleted too.'
            )
            delete_dialog.open()
