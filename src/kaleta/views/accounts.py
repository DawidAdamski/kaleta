from __future__ import annotations

from collections import defaultdict

from nicegui import app, ui

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


def _group_icon(by: str, name: str, accts: list[Account]) -> str:
    labels = _type_labels()
    if by == "type":
        rev = {v: k for k, v in labels.items()}
        atype = rev.get(name)
        return _TYPE_ICONS.get(atype, "folder") if atype else "folder"
    return "account_balance" if accts and accts[0].institution_id else "folder_off"


def register() -> None:
    @ui.page("/accounts")
    async def accounts_page() -> None:
        async with AsyncSessionFactory() as session:
            account_list: list[Account] = await AccountService(session).list()
            institution_list: list[Institution] = await InstitutionService(session).list()

        inst_options: dict[int, str] = {0: t("common.none")}
        inst_options.update({i.id: i.name for i in institution_list})

        # ── Persistent state ───────────────────────────────────────────────────
        state: dict = {
            "group_by": app.storage.user.get("accounts_group_by", "type"),
            "selected_id": None,
        }
        # Collapsed group keys stored in user storage so they survive page reloads.
        # Key format: "{group_by}:{group_name}"
        _collapsed: set[str] = set(app.storage.user.get("accounts_collapsed", []))

        def _is_expanded(gk: str) -> bool:
            return gk not in _collapsed

        def _set_expanded(gk: str, expanded: bool) -> None:
            if expanded:
                _collapsed.discard(gk)
            else:
                _collapsed.add(gk)
            app.storage.user["accounts_collapsed"] = list(_collapsed)

        def _set_group(by: str) -> None:
            state["group_by"] = by
            app.storage.user["accounts_group_by"] = by
            group_buttons.refresh()
            account_table.refresh()

        with page_layout(t("accounts.title")):

            # ── Dialogs (defined first so handlers below can reference them) ──

            with ui.dialog() as add_dialog, ui.card().classes("w-[420px]"):
                ui.label(t("accounts.add")).classes("text-lg font-bold mb-2")
                add_name = ui.input(f"{t('common.name')} *").classes("w-full")
                add_type = ui.select(
                    {at.value: _type_labels()[at] for at in AccountType},
                    label=t("common.type"),
                    value=AccountType.CHECKING.value,
                ).classes("w-full")
                add_currency = ui.select(
                    COMMON_CURRENCIES, label=t("accounts.currency"), value="PLN",
                ).classes("w-full").tooltip(t("accounts.currency_hint"))
                add_balance = ui.number(
                    t("common.balance"), value=0, format="%.2f"
                ).classes("w-full")
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
                        acc = await AccountService(session).get(acc.id)
                    if acc:
                        account_list.append(acc)
                    account_table.refresh()
                    ui.notify(t("accounts.created"), type="positive")
                    add_dialog.close()

                with ui.row().classes("w-full justify-end gap-2 mt-4"):
                    ui.button(t("common.cancel"), on_click=add_dialog.close).props("flat")
                    ui.button(t("common.save"), on_click=save_add).props("color=primary")
                ui.keyboard(on_key=lambda e: (
                    save_add() if e.key == "Enter" and e.action.keydown else
                    add_dialog.close() if e.key == "Escape" and e.action.keydown else None
                ))

            with ui.dialog() as edit_dialog, ui.card().classes("w-[420px]"):
                ui.label(t("accounts.edit")).classes("text-lg font-bold mb-2")
                edit_name = ui.input(f"{t('common.name')} *").classes("w-full")
                edit_type = ui.select(
                    {at.value: _type_labels()[at] for at in AccountType},
                    label=t("common.type"),
                ).classes("w-full")
                edit_currency = ui.select(
                    COMMON_CURRENCIES, label=t("accounts.currency"), value="PLN",
                ).classes("w-full").tooltip(t("accounts.currency_hint"))
                edit_inst = ui.select(
                    inst_options, label=t("common.institution"), value=0
                ).classes("w-full")

                async def save_edit() -> None:
                    aid = state["selected_id"]
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
                ui.keyboard(on_key=lambda e: (
                    save_edit() if e.key == "Enter" and e.action.keydown else
                    edit_dialog.close() if e.key == "Escape" and e.action.keydown else None
                ))

            with ui.dialog() as delete_dialog, ui.card().classes("w-96"):
                delete_label = ui.label("").classes("text-base mb-4")

                async def confirm_delete() -> None:
                    aid = state["selected_id"]
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
                    ui.button(
                        t("common.delete"), on_click=confirm_delete
                    ).props("color=negative")

            # ── Action handlers (defined after dialogs, before table) ─────────

            def _open_add() -> None:
                add_name.set_value("")
                add_type.set_value(AccountType.CHECKING.value)
                add_currency.set_value("PLN")
                add_balance.set_value(0)
                add_inst.set_value(0)
                add_dialog.open()

            def _open_edit(a: Account) -> None:
                state["selected_id"] = a.id
                edit_name.set_value(a.name)
                edit_type.set_value(a.type.value)
                edit_currency.set_value(a.currency)
                edit_inst.set_value(a.institution_id or 0)
                edit_dialog.open()

            def _open_delete(a: Account) -> None:
                state["selected_id"] = a.id
                delete_label.set_text(t("accounts.delete_confirm", name=a.name))
                delete_dialog.open()

            # ── Header ────────────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("accounts.title")).classes("text-2xl font-bold")
                with ui.row().classes("gap-2 items-center"):
                    ui.label(t("accounts.group_by")).classes("text-sm text-grey-6")

                    @ui.refreshable
                    def group_buttons() -> None:
                        for key, label in [
                            ("type", t("accounts.group_type")),
                            ("institution", t("accounts.group_institution")),
                        ]:
                            active = state["group_by"] == key
                            ui.button(
                                label,
                                on_click=lambda k=key: _set_group(k),
                            ).props(
                                ("color=primary" if active else "outline color=primary")
                                + " dense rounded"
                            )

                    group_buttons()
                    ui.button(
                        t("accounts.add"), icon="add", on_click=_open_add
                    ).props("color=primary")

            # ── Account table ─────────────────────────────────────────────────
            @ui.refreshable
            def account_table() -> None:
                labels = _type_labels()
                by = state["group_by"]

                groups: dict[str, list[Account]] = defaultdict(list)
                if by == "institution":
                    inst_by_id: dict[int, str] = {i.id: i.name for i in institution_list}
                    for a in account_list:
                        key = inst_by_id.get(
                            a.institution_id or -1,  # type: ignore[arg-type]
                            t("accounts.no_institution"),
                        )
                        groups[key].append(a)
                else:
                    for a in account_list:
                        groups[labels.get(a.type, a.type.value)].append(a)

                if not groups:
                    ui.label(t("accounts.no_accounts")).classes("text-grey-6 mt-8")
                    return

                for group_name in sorted(groups.keys()):
                    accts = groups[group_name]
                    group_key = f"{by}:{group_name}"
                    exp = (
                        ui.expansion(
                            group_name,
                            icon=_group_icon(by, group_name, accts),
                            value=_is_expanded(group_key),
                        )
                        .classes("w-full border rounded-lg mb-2")
                    )
                    exp.on("after-show", lambda gk=group_key: _set_expanded(gk, True))
                    exp.on("after-hide", lambda gk=group_key: _set_expanded(gk, False))

                    with exp:
                        # Column headers
                        with ui.row().classes(
                            "w-full px-4 py-1 text-xs text-grey-6 font-medium border-b"
                        ):
                            ui.label(t("common.name")).classes("flex-1")
                            if by == "type":
                                ui.label(t("common.institution")).classes("w-44")
                            else:
                                ui.label(t("common.type")).classes("w-44")
                            ui.label(t("common.balance")).classes("w-44 text-right pr-2")
                            ui.label("").classes("w-20")

                        # Account rows — Python buttons, no JS event emission
                        for a in accts:
                            with ui.row().classes("w-full px-4 py-2 items-center border-b"):
                                ui.label(a.name).classes("flex-1 font-medium")
                                if by == "type":
                                    ui.label(
                                        a.institution.name if a.institution else "—"
                                    ).classes("w-44 text-grey-6 text-sm")
                                else:
                                    ui.label(labels.get(a.type, a.type.value)).classes(
                                        "w-44 text-grey-6 text-sm"
                                    )
                                ui.label(f"{a.balance:,.2f} {a.currency}").classes(
                                    "w-44 text-right font-mono text-sm pr-2"
                                )
                                with ui.row().classes("w-20 justify-end gap-1"):
                                    ui.button(
                                        icon="edit",
                                        on_click=lambda acc=a: _open_edit(acc),
                                    ).props("flat round dense color=primary size=sm")
                                    ui.button(
                                        icon="delete",
                                        on_click=lambda acc=a: _open_delete(acc),
                                    ).props("flat round dense color=negative size=sm")

            account_table()
