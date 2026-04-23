"""Housekeeping page — surface duplicate candidates and offer one-click merge."""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.services.dedupe_service import (
    CategoryGroup,
    DedupeService,
    PayeeGroup,
    TxGroup,
)
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    BODY_MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)


def register() -> None:
    @ui.page("/housekeeping")
    async def housekeeping_page() -> None:
        async with AsyncSessionFactory() as session:
            svc = DedupeService(session)
            dup_window_days = int(
                app.storage.user.get("housekeeping_duplicate_days", 0) or 0
            ) or None
            tx_groups = await svc.duplicate_transactions(window_days=dup_window_days)
            payee_groups = await svc.similar_payees()
            category_groups = await svc.redundant_categories()

        with page_layout(t("housekeeping.title"), wide=True):
            # ── Header ───────────────────────────────────────────────────
            with ui.column().classes("gap-1"):
                ui.label(t("housekeeping.title")).classes(PAGE_TITLE)
                ui.label(t("housekeeping.subtitle")).classes(BODY_MUTED)

            # ── Shared confirm dialog ────────────────────────────────────
            pending: dict[str, Any] = {"action": None, "count": 0}

            with ui.dialog() as confirm_dialog, ui.card().classes("w-[440px] gap-3"):
                ui.label(t("housekeeping.merge_confirm_title")).classes(
                    "text-lg font-bold"
                )
                confirm_body = ui.label("").classes(BODY_MUTED)
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=confirm_dialog.close).props(
                        "flat"
                    )
                    confirm_btn = ui.button(
                        t("housekeeping.merge_confirm_confirm"), icon="merge_type"
                    ).props("color=negative unelevated")

            async def _run_pending() -> None:
                action = pending["action"]
                confirm_dialog.close()
                if action is None:
                    return
                await action()
                ui.navigate.reload()

            confirm_btn.on_click(_run_pending)

            def _ask_confirm(count: int, action: Any) -> None:
                pending["action"] = action
                pending["count"] = count
                confirm_body.set_text(
                    t("housekeeping.merge_confirm_body", count=count)
                )
                confirm_dialog.open()

            # ── Duplicate transactions ───────────────────────────────────
            _render_tx_section(tx_groups, _ask_confirm)

            # ── Similar payees ───────────────────────────────────────────
            _render_payee_section(payee_groups, _ask_confirm)

            # ── Redundant categories ─────────────────────────────────────
            _render_category_section(category_groups, _ask_confirm)


# ── Sections ─────────────────────────────────────────────────────────────────


def _section_header(title_key: str, hint_key: str, count: int) -> None:
    with ui.row().classes("w-full items-center gap-3"):
        ui.label(t(title_key)).classes(SECTION_HEADING)
        if count > 0:
            ui.badge(t("housekeeping.group_count", count=count)).props(
                "color=amber-7 rounded"
            )
    ui.label(t(hint_key)).classes(BODY_MUTED)


def _render_tx_section(groups: list[TxGroup], ask_confirm: Any) -> None:
    with ui.card().classes(SECTION_CARD):
        _section_header(
            "housekeeping.transactions_heading",
            "housekeeping.transactions_hint",
            len(groups),
        )
        if not groups:
            ui.label(t("housekeeping.transactions_empty")).classes(
                f"{BODY_MUTED} mt-2"
            )
            return
        for g in groups:
            _render_tx_group(g, ask_confirm)


def _render_payee_section(groups: list[PayeeGroup], ask_confirm: Any) -> None:
    with ui.card().classes(SECTION_CARD):
        _section_header(
            "housekeeping.payees_heading",
            "housekeeping.payees_hint",
            len(groups),
        )
        if not groups:
            ui.label(t("housekeeping.payees_empty")).classes(f"{BODY_MUTED} mt-2")
            return
        for g in groups:
            _render_payee_group(g, ask_confirm)


def _render_category_section(groups: list[CategoryGroup], ask_confirm: Any) -> None:
    with ui.card().classes(SECTION_CARD):
        _section_header(
            "housekeeping.categories_heading",
            "housekeeping.categories_hint",
            len(groups),
        )
        if not groups:
            ui.label(t("housekeeping.categories_empty")).classes(
                f"{BODY_MUTED} mt-2"
            )
            return
        for g in groups:
            _render_category_group(g, ask_confirm)


# ── Group renderers ──────────────────────────────────────────────────────────


def _render_tx_group(group: TxGroup, ask_confirm: Any) -> None:
    # Default keeper = oldest date. User can change.
    keeper_holder = {"id": group.items[0].id}
    keeper_options: dict[int, str] = {
        item.id: f"#{item.id} · {item.date} · {item.description[:40] or '—'}"
        for item in group.items
    }

    with ui.element("div").classes(
        "w-full mt-3 p-3 rounded border border-slate-200/30"
    ):
        for item in group.items:
            with ui.row().classes("w-full items-center gap-3 py-1"):
                ui.label(str(item.date)).classes("w-24 text-xs text-slate-500")
                ui.label(item.description[:60] or "—").classes("flex-1 text-sm")
                amount_cls = AMOUNT_INCOME if item.amount >= 0 else AMOUNT_EXPENSE
                ui.label(f"{item.amount:,.2f}").classes(
                    f"{amount_cls} w-24 text-right text-sm"
                )
                ui.label(f"#{item.id}").classes("w-16 text-xs text-slate-500 text-right")

        with ui.row().classes("w-full items-center gap-3 mt-2"):
            keeper_sel = (
                ui.select(
                    options=keeper_options,
                    label=t("housekeeping.keeper_label"),
                    value=keeper_holder["id"],
                )
                .props("dense outlined")
                .classes("flex-1")
            )

            def _on_change(_e: object = None, holder: dict[str, int] = keeper_holder) -> None:
                if keeper_sel.value is not None:
                    holder["id"] = int(keeper_sel.value)

            keeper_sel.on("update:model-value", _on_change)

            async def _merge() -> None:
                keeper_id = keeper_holder["id"]
                other_ids = [item.id for item in group.items if item.id != keeper_id]
                async with AsyncSessionFactory() as s:
                    deleted = await DedupeService(s).merge_transactions(
                        keeper_id=keeper_id, other_ids=other_ids
                    )
                ui.notify(
                    t("housekeeping.merged_tx", count=deleted), type="positive"
                )

            delete_count = len(group.items) - 1
            ui.button(
                t("housekeeping.merge"),
                icon="merge_type",
                on_click=lambda _e, a=_merge, c=delete_count: ask_confirm(c, a),
            ).props("color=primary unelevated size=sm")


def _render_payee_group(group: PayeeGroup, ask_confirm: Any) -> None:
    # Default keeper = highest transaction_count, tie-breaker = lowest id.
    default_keeper = max(group.items, key=lambda x: (x.transaction_count, -x.id))
    keeper_holder = {"id": default_keeper.id}
    keeper_options: dict[int, str] = {
        item.id: f"{item.name} ({item.transaction_count})" for item in group.items
    }

    with ui.element("div").classes(
        "w-full mt-3 p-3 rounded border border-slate-200/30"
    ):
        for item in group.items:
            with ui.row().classes("w-full items-center gap-3 py-1"):
                ui.label(item.name).classes("flex-1 text-sm")
                ui.label(
                    t("housekeeping.transaction_count", count=item.transaction_count)
                ).classes("text-xs text-slate-500 w-32 text-right")

        with ui.row().classes("w-full items-center gap-3 mt-2"):
            keeper_sel = (
                ui.select(
                    options=keeper_options,
                    label=t("housekeeping.keeper_label"),
                    value=keeper_holder["id"],
                )
                .props("dense outlined")
                .classes("flex-1")
            )

            def _on_change(_e: object = None, holder: dict[str, int] = keeper_holder) -> None:
                if keeper_sel.value is not None:
                    holder["id"] = int(keeper_sel.value)

            keeper_sel.on("update:model-value", _on_change)

            async def _merge() -> None:
                keeper_id = keeper_holder["id"]
                other_ids = [item.id for item in group.items if item.id != keeper_id]
                async with AsyncSessionFactory() as s:
                    merged = await DedupeService(s).merge_payees(
                        keeper_id=keeper_id, other_ids=other_ids
                    )
                ui.notify(
                    t("housekeeping.merged_payees", count=merged), type="positive"
                )

            delete_count = len(group.items) - 1
            ui.button(
                t("housekeeping.merge"),
                icon="merge_type",
                on_click=lambda _e, a=_merge, c=delete_count: ask_confirm(c, a),
            ).props("color=primary unelevated size=sm")


def _render_category_group(group: CategoryGroup, ask_confirm: Any) -> None:
    default_keeper = max(group.items, key=lambda x: (x.transaction_count, -x.id))
    keeper_holder = {"id": default_keeper.id}
    keeper_options: dict[int, str] = {
        item.id: f"{item.name} ({item.transaction_count})" for item in group.items
    }

    with ui.element("div").classes(
        "w-full mt-3 p-3 rounded border border-slate-200/30"
    ):
        for item in group.items:
            with ui.row().classes("w-full items-center gap-3 py-1"):
                ui.label(item.name).classes("flex-1 text-sm")
                ui.label(
                    t("housekeeping.transaction_count", count=item.transaction_count)
                ).classes("text-xs text-slate-500 w-32 text-right")

        with ui.row().classes("w-full items-center gap-3 mt-2"):
            keeper_sel = (
                ui.select(
                    options=keeper_options,
                    label=t("housekeeping.keeper_label"),
                    value=keeper_holder["id"],
                )
                .props("dense outlined")
                .classes("flex-1")
            )

            def _on_change(_e: object = None, holder: dict[str, int] = keeper_holder) -> None:
                if keeper_sel.value is not None:
                    holder["id"] = int(keeper_sel.value)

            keeper_sel.on("update:model-value", _on_change)

            async def _merge() -> None:
                keeper_id = keeper_holder["id"]
                other_ids = [item.id for item in group.items if item.id != keeper_id]
                async with AsyncSessionFactory() as s:
                    merged = await DedupeService(s).merge_categories(
                        keeper_id=keeper_id, other_ids=other_ids
                    )
                ui.notify(
                    t("housekeeping.merged_categories", count=merged),
                    type="positive",
                )

            delete_count = len(group.items) - 1
            ui.button(
                t("housekeeping.merge"),
                icon="merge_type",
                on_click=lambda _e, a=_merge, c=delete_count: ask_confirm(c, a),
            ).props("color=primary unelevated size=sm")
