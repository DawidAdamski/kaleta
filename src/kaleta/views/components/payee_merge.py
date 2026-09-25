# SPDX-License-Identifier: AGPL-3.0-or-later
"""Payee merge suggestions — shared by the Housekeeping and Payees pages.

One suggested group renders as its members, a keeper picker and an optional
new name for the keeper ("LIDL SP. Z O.O." + "Lidl 1234 Warszawa" → "Lidl").
Merging goes through a confirm dialog, since it deletes rows for good.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import DedupeService, with_session
from kaleta.services.dedupe_service import PayeeGroup
from kaleta.views.error_handling import handle_kaleta_error
from kaleta.views.theme import BODY_MUTED

MergeAction = Callable[[], Awaitable[None]]


class MergeConfirmDialog:
    """Ask before a merge runs; call *on_done* once it has."""

    def __init__(self, on_done: Callable[[], Any]) -> None:
        self._on_done = on_done
        self._action: MergeAction | None = None
        with ui.dialog() as self._dialog, ui.card().classes("w-[440px] gap-3"):
            ui.label(t("housekeeping.merge_confirm_title")).classes("text-lg font-bold")
            self._body = ui.label("").classes(BODY_MUTED)
            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=self._dialog.close).props("flat")
                ui.button(
                    t("housekeeping.merge_confirm_confirm"),
                    icon="merge_type",
                    on_click=self._run,
                ).props("color=negative unelevated")

    def ask(self, count: int, action: MergeAction) -> None:
        self._action = action
        self._body.set_text(t("housekeeping.merge_confirm_body", count=count))
        self._dialog.open()

    async def _run(self) -> None:
        action = self._action
        self._dialog.close()
        if action is None:
            return
        try:
            await action()
        except Exception as exc:
            if handle_kaleta_error(exc):
                return
            raise
        result = self._on_done()
        if isinstance(result, Awaitable):
            await result


class PayeeMergeSuggestion:
    """One suggested group of look-alike payees, with its merge controls."""

    def __init__(self, group: PayeeGroup, ask_confirm: Callable[[int, MergeAction], None]) -> None:
        self._group = group
        # Default keeper = highest transaction_count, tie-breaker = lowest id.
        default_keeper = max(group.items, key=lambda x: (x.transaction_count, -x.id))
        self._keeper_id = default_keeper.id
        self._render(ask_confirm)

    def _render(self, ask_confirm: Callable[[int, MergeAction], None]) -> None:
        keeper_options: dict[int, str] = {
            item.id: f"{item.name} ({item.transaction_count})" for item in self._group.items
        }
        with (
            ui.element("div")
            .classes("w-full mt-3 p-3 rounded border border-slate-200/30")
            .props("data-merge-suggestion")
        ):
            for item in self._group.items:
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
                        value=self._keeper_id,
                    )
                    .props("dense outlined")
                    .classes("flex-1")
                )
                keeper_sel.on(
                    "update:model-value",
                    lambda _e: self._set_keeper(keeper_sel.value),
                )
                self._new_name = (
                    ui.input(
                        t("housekeeping.new_name_label"),
                        placeholder=t("housekeeping.new_name_placeholder"),
                    )
                    .props("dense outlined maxlength=200")
                    .classes("flex-1")
                )
                delete_count = len(self._group.items) - 1
                ui.button(
                    t("housekeeping.merge"),
                    icon="merge_type",
                    on_click=lambda _e: ask_confirm(delete_count, self._merge),
                ).props("color=primary unelevated size=sm")

    def _set_keeper(self, value: object) -> None:
        if value is not None:
            self._keeper_id = int(str(value))

    async def _merge(self) -> None:
        keeper_id = self._keeper_id
        other_ids = [item.id for item in self._group.items if item.id != keeper_id]
        new_name = (self._new_name.value or "").strip() or None

        async def _run(session: Any) -> int:
            return await DedupeService(session).merge_payees(
                keeper_id=keeper_id, other_ids=other_ids, new_name=new_name
            )

        merged = await with_session(_run)
        ui.notify(t("housekeeping.merged_payees", count=merged), type="positive")
