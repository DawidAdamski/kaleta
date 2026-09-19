# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only detail dialog for an upcoming planned row in the ledger."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.planned_transaction import RecurrenceFrequency
from kaleta.services import PlannedTransactionService, with_session
from kaleta.views.components.amount_label import format_signed_amount, signed_amount_class

_AMOUNT_CLS = "text-xl font-semibold k-mono"


def _frequency_label(frequency: RecurrenceFrequency, interval: int) -> str:
    base = t(f"planned.freq_{frequency.value}")
    return base if interval == 1 else f"{t('planned.every')} {interval} × {base}"


def parse_planned_row_key(row_key: str) -> tuple[int, datetime.date] | None:
    """Split a planned row's ``planned:<id>:<date>`` key back into its parts.

    The browser sends back whatever the row carried, so a key that is not one
    of ours — a stale event, a hand-edited payload — has to come back as
    ``None`` rather than raise inside the click handler.
    """
    parts = row_key.split(":") if isinstance(row_key, str) else []
    if len(parts) != 3 or parts[0] != "planned":
        return None
    try:
        return int(parts[1]), datetime.date.fromisoformat(parts[2])
    except ValueError:
        return None


@dataclass
class PlannedDialogContext:
    dialog: ui.dialog
    open_for_row_key: Any


def build_planned_dialog() -> PlannedDialogContext:
    """The plan behind an upcoming row, shown but not edited.

    The ledger shows a future occurrence, and an occurrence has nothing of its
    own to save — the template it came from does. Editing that template lives
    on the Planned Transactions page, so this dialog reads the plan out and
    hands the user a link there rather than a second editor that could drift
    from the first.
    """
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[420px] gap-2"):
        ui.label(t("transactions.planned_detail_title")).classes("text-lg font-bold")
        name_label = ui.label("").classes("text-base")
        amount_label = ui.label("").classes(_AMOUNT_CLS)

        detail_rows = ui.column().classes("w-full gap-1 mt-2")

        ui.label(t("transactions.planned_detail_hint")).classes("text-xs text-slate-500 mt-2")

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.close"), on_click=dialog.close).props("flat")
            ui.button(
                t("transactions.planned_open_plan"),
                icon="open_in_new",
                on_click=lambda: ui.navigate.to("/planned"),
            ).props("color=primary")

    def _detail(label: str, value: str) -> None:
        with ui.row().classes("w-full items-center gap-3"):
            ui.label(label).classes("text-sm text-slate-500 w-28")
            ui.label(value).classes("text-sm")

    async def open_for_row_key(event: Any) -> None:
        parsed = parse_planned_row_key(getattr(event, "args", event))
        if parsed is None:
            return
        planned_id, occurrence_date = parsed

        async def _load(session: Any) -> Any:
            return await PlannedTransactionService(session).get(planned_id)

        plan = await with_session(_load)
        if plan is None:
            # The plan was deleted between the page being drawn and the row
            # being clicked. Saying so beats a click that does nothing.
            ui.notify(t("transactions.planned_gone"), type="warning")
            return

        name_label.set_text(plan.name)
        amount_label.set_text(format_signed_amount(plan.amount, plan.type))
        tone = signed_amount_class(plan.amount, plan.type)
        amount_label.classes(replace=f"{_AMOUNT_CLS} {tone}")

        detail_rows.clear()
        with detail_rows:
            _detail(t("common.date"), str(occurrence_date))
            _detail(t("common.account"), plan.account.name if plan.account else "—")
            _detail(t("common.category"), plan.category.name if plan.category else "—")
            _detail(t("common.type"), t(f"common.{plan.type.value}"))
            _detail(
                t("transactions.planned_detail_frequency"),
                _frequency_label(plan.frequency, plan.interval),
            )
            if plan.description:
                _detail(t("common.description"), plan.description)
        dialog.open()

    return PlannedDialogContext(dialog=dialog, open_for_row_key=open_for_row_key)
