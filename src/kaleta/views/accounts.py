from __future__ import annotations

from collections import defaultdict

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.account import Account, AccountType
from kaleta.models.institution import Institution
from kaleta.schemas.account import AccountCreate, AccountUpdate
from kaleta.services import AccountService, InstitutionService
from kaleta.views.layout import page_layout

COMMON_CURRENCIES: list[str] = [
    "PLN", "EUR", "USD", "GBP", "CHF", "CZK", "HUF", "NOK", "SEK", "DKK",
]


_TYPE_ICONS: dict[str, str] = {
    AccountType.CHECKING: "account_balance_wallet",
    AccountType.SAVINGS: "savings",
    AccountType.CASH: "payments",
    AccountType.CREDIT: "credit_card",
}


def _type_labels() -> dict[str, str]:
    return {
        AccountType.CHECKING: t("accounts.checking"),
        AccountType.SAVINGS: t("accounts.savings"),
        AccountType.CASH: t("accounts.cash"),
        AccountType.CREDIT: t("accounts.credit"),
    }


def _col_type() -> dict:
    return {
        "name": "type",
        "label": t("common.type"),
        "field": "type",
        "align": "left",
        "sortable": True,
    }


def _col_inst() -> dict:
    return {
        "name": "institution",
        "label": t("common.institution"),
        "field": "institution_name",
        "align": "left",
        "sortable": True,
    }


def _col_name() -> dict:
    return {
        "name": "name",
        "label": t("common.name"),
        "field": "name",
        "align": "left",
        "sortable": True,
    }


def _col_bal() -> dict:
    return {
        "name": "balance",
        "label": t("common.balance"),
        "field": "balance",
        "align": "right",
        "sortable": True,
    }


def _col_actions() -> dict:
    return {"name": "actions", "label": "", "field": "actions", "align": "right"}


def _columns_for(by: str) -> list[dict]:
    extra = _col_inst() if by == "type" else _col_type()
    return [_col_name(), extra, _col_bal(), _col_actions()]


def _account_row(a: Account) -> dict:
    labels = _type_labels()
    return {
        "id": a.id,
        "name": a.name,
        "type": labels.get(a.type, a.type.value),
        "balance": f"{a.balance:,.2f} {a.currency}",
        "institution_id": a.institution_id,
        "institution_name": a.institution.name if a.institution else "",
        "currency": a.currency,
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

        with page_layout(t("accounts.title")):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("accounts.title")).classes("text-2xl font-bold")
                with ui.row().classes("gap-2 items-center"):
                    ui.label(t("accounts.group_by")).classes("text-sm text-grey-6")
                    group_toggle = ui.toggle(
                        {
                            "type": t("accounts.group_type"),
                            "institution": t("accounts.group_institution"),
                        },
                        value="type",
                    ).props("dense")
                    ui.button(
                        t("accounts.add"), icon="add", on_click=lambda: _open_add()
                    ).props("color=primary")

            @ui.refreshable
            def account_table() -> None:
                labels = _type_labels()
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
                        groups[labels.get(a.type, a.type.value)].append(a)

                if not groups:
                    ui.label(t("accounts.no_accounts")).classes("text-grey-6 mt-8")
                    return

                for group_name in sorted(groups.keys()):
                    accts = groups[group_name]
                    with (
                        ui.expansion(group_name, icon=_group_icon(by, group_name, accts))
                        .classes("w-full border rounded-lg mb-2")
                        .props("default-opened")
                    ):
                        rows = [_account_row(a) for a in accts]
                        table = ui.table(
                            columns=_columns_for(by), rows=rows, row_key="id"
                        ).classes("w-full")
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
                labels = _type_labels()
                if by == "type":
                    rev = {v: k for k, v in labels.items()}
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
            ui.label(t("accounts.add")).classes("text-lg font-bold mb-2")
            add_name = ui.input(f"{t('common.name')} *").classes("w-full")
            add_type = ui.select(
                {at.value: _type_labels()[at] for at in AccountType},
                label=t("common.type"),
                value=AccountType.CHECKING.value,
            ).classes("w-full")
            add_currency = ui.select(
                COMMON_CURRENCIES,
                label=t("accounts.currency"),
                value="PLN",
            ).classes("w-full").tooltip(t("accounts.currency_hint"))
            add_balance = ui.number(t("common.balance"), value=0, format="%.2f").classes("w-full")
            add_inst = ui.select(
                inst_options, label=t("common.institution"), value=0
            ).classes("w-full")

            async def save_add() -> None:
                if not add_name.value or not add_name.value.strip():
                    ui.notify(t("accounts.name_required"), type="negative")
                    return
                inst_id = add_inst.value if add_inst.value != 0 else None
                data = AccountCreate(
                    name=add_name.value.strip(),
                    type=AccountType(add_type.value),
                    balance=add_balance.value,
                    currency=add_currency.value or "PLN",
                    institution_id=inst_id,
                )
                async with AsyncSessionFactory() as session:
                    acc = await AccountService(session).create(data)
                    # reload with institution relationship
                    acc = await AccountService(session).get(acc.id)
                if acc:
                    account_list.append(acc)
                account_table.refresh()
                ui.notify(t("accounts.created"), type="positive")
                add_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=add_dialog.close).props("flat")
                ui.button(t("common.save"), on_click=save_add).props("color=primary")

        # ── Edit dialog ───────────────────────────────────────────────────────
        with ui.dialog() as edit_dialog, ui.card().classes("w-[420px]"):
            ui.label(t("accounts.edit")).classes("text-lg font-bold mb-2")
            edit_name = ui.input(f"{t('common.name')} *").classes("w-full")
            edit_type = ui.select(
                {at.value: _type_labels()[at] for at in AccountType},
                label=t("common.type"),
            ).classes("w-full")
            edit_currency = ui.select(
                COMMON_CURRENCIES,
                label=t("accounts.currency"),
                value="PLN",
            ).classes("w-full").tooltip(t("accounts.currency_hint"))
            edit_inst = ui.select(
                inst_options, label=t("common.institution"), value=0
            ).classes("w-full")

            async def save_edit() -> None:
                aid = selected_id[0]
                if aid is None:
                    return
                if not edit_name.value or not edit_name.value.strip():
                    ui.notify(t("accounts.name_required"), type="negative")
                    return
                inst_id = edit_inst.value if edit_inst.value != 0 else None
                data = AccountUpdate(
                    name=edit_name.value.strip(),
                    type=AccountType(edit_type.value),
                    currency=edit_currency.value or "PLN",
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
                ui.notify(t("accounts.updated"), type="positive")
                edit_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=edit_dialog.close).props("flat")
                ui.button(t("common.save"), on_click=save_edit).props("color=primary")

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
                ui.notify(t("accounts.deleted"), type="positive")
                delete_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")
                ui.button(t("common.delete"), on_click=confirm_delete).props("color=negative")

        def _open_add() -> None:
            add_name.set_value("")
            add_type.set_value(AccountType.CHECKING.value)
            add_currency.set_value("PLN")
            add_balance.set_value(0)
            add_inst.set_value(0)
            add_dialog.open()

        def _open_edit_row(row: dict) -> None:
            selected_id[0] = row["id"]
            edit_name.set_value(row["name"])
            labels = _type_labels()
            rev = {v: k for k, v in labels.items()}
            atype = rev.get(row["type"])
            edit_type.set_value(atype.value if atype else AccountType.CHECKING.value)
            edit_currency.set_value(row.get("currency") or "PLN")
            inst_id = row.get("institution_id") or 0
            edit_inst.set_value(inst_id)
            edit_dialog.open()

        def _open_delete_row(row: dict) -> None:
            selected_id[0] = row["id"]
            delete_label.set_text(t("accounts.delete_confirm", name=row["name"]))
            delete_dialog.open()
