# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unplanned expenses radar — irregular repeat costs, one click from a plan."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.schemas.category import CategoryType
from kaleta.schemas.planned_transaction import RecurrenceFrequency
from kaleta.schemas.unplanned_radar import RadarCandidate, RadarPlannedRow, RadarSummary
from kaleta.services import (
    AccountService,
    CategoryService,
    UnplannedRadarService,
    with_session,
)
from kaleta.services.unplanned_radar_service import summarise
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.layout import page_layout
from kaleta.views.theme import AMOUNT_EXPENSE, BODY_MUTED, PAGE_TITLE, SECTION_CARD, SECTION_HEADING

_SAFETY_FUNDS_URL = "/wizard/safety-funds"
_PAYMENT_CALENDAR_URL = "/payment-calendar"


def _fmt_amount(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _fmt_date(value: datetime.date) -> str:
    return value.isoformat()


def cadence_label(frequency: RecurrenceFrequency, interval: int) -> str:
    """Human wording for the rhythm the radar inferred."""
    if frequency == RecurrenceFrequency.YEARLY:
        return t("unplanned_radar.cadence_yearly")
    return t("unplanned_radar.cadence_monthly", interval=interval)


def register() -> None:
    @ui.page("/wizard/unplanned-radar")
    async def unplanned_radar_page() -> None:
        async def _load(session: Any) -> tuple[Any, ...]:
            svc = UnplannedRadarService(session)
            candidates = await svc.detect()
            planned_rows = await svc.planned_with_history()
            accounts = await AccountService(session).list()
            categories = await CategoryService(session).list()
            return candidates, planned_rows, accounts, categories

        candidates, planned_rows, accounts, categories = await with_session(_load)

        summary = summarise(candidates)
        account_opts = {a.id: a.name for a in accounts}
        category_opts = CategoryService.build_option_labels(
            [c for c in categories if c.type == CategoryType.EXPENSE]
        )

        with page_layout(t("unplanned_radar.title"), wide=True):
            with ui.column().classes("gap-1"):
                ui.label(t("unplanned_radar.title")).classes(PAGE_TITLE)
                ui.label(t("unplanned_radar.subtitle")).classes(BODY_MUTED)

            open_plan_dialog = _build_plan_dialog(
                account_opts=account_opts,
                category_opts=category_opts,
            )

            _render_summary(summary)

            with ui.card().classes(SECTION_CARD):
                ui.label(t("unplanned_radar.candidates_heading")).classes(SECTION_HEADING)
                ui.label(t("unplanned_radar.candidates_hint")).classes(BODY_MUTED)
                if not candidates:
                    ui.label(t("unplanned_radar.candidates_empty")).classes(f"{BODY_MUTED} mt-2")
                else:
                    for candidate in candidates:
                        _render_candidate_row(candidate, on_plan=open_plan_dialog)

            _render_planned_section(planned_rows)


def _render_summary(summary: RadarSummary) -> None:
    with (
        ui.card().classes(SECTION_CARD),
        ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"),
    ):
        with ui.column().classes("gap-1 flex-1"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("build_circle", size="1.4rem").classes("text-primary")
                ui.label(t("unplanned_radar.summary_heading")).classes(SECTION_HEADING)
            if summary.candidate_count:
                ui.label(
                    t(
                        "unplanned_radar.summary_body",
                        count=summary.candidate_count,
                        yearly=_fmt_amount(summary.yearly_total),
                        monthly=_fmt_amount(summary.monthly_equivalent),
                    )
                ).classes(BODY_MUTED)
            else:
                ui.label(t("unplanned_radar.summary_empty")).classes(BODY_MUTED)
        ui.button(
            t("unplanned_radar.summary_cta"),
            icon="savings",
            on_click=lambda: ui.navigate.to(_SAFETY_FUNDS_URL),
        ).props("flat color=primary size=sm")


def _render_candidate_row(
    candidate: RadarCandidate,
    *,
    on_plan: Callable[[RadarCandidate], None],
) -> None:
    with ui.row().classes("w-full items-center gap-3 py-2 border-b border-slate-100"):
        ui.icon("search", size="1.3rem").classes("text-primary")
        with ui.column().classes("flex-1 gap-0"):
            ui.label(candidate.source_name).classes("text-sm font-medium")
            ui.label(
                t(
                    "unplanned_radar.occurrences",
                    count=candidate.occurrences,
                    date=_fmt_date(candidate.last_seen_at),
                )
            ).classes("text-xs text-slate-500")
            ui.label(
                t(
                    "unplanned_radar.occurrence_dates",
                    dates=", ".join(_fmt_date(d) for d in candidate.occurrence_dates),
                )
            ).classes("text-xs text-slate-400")
        with ui.column().classes("gap-0 items-end w-40"):
            ui.label(cadence_label(candidate.frequency, candidate.interval)).classes(
                "text-xs text-slate-500"
            )
            ui.label(
                t("unplanned_radar.next_expected", date=_fmt_date(candidate.next_expected_at))
            ).classes("text-xs text-slate-500")
        with ui.column().classes("gap-0 items-end w-32"):
            ui.label(_fmt_amount(candidate.typical_amount)).classes(f"{AMOUNT_EXPENSE} text-sm")
            ui.label(
                t(
                    "unplanned_radar.yearly_estimate",
                    amount=_fmt_amount(candidate.yearly_estimate),
                )
            ).classes("text-xs text-slate-500")
        ui.button(
            t("unplanned_radar.plan_it"),
            icon="event_repeat",
            on_click=lambda _e, c=candidate: on_plan(c),
        ).props("color=primary unelevated size=sm")
        dismiss_label = t("unplanned_radar.dismiss")
        ui.button(
            icon="close",
            on_click=lambda _e, c=candidate: _dismiss(c),
        ).props(f'flat dense round color=grey-7 aria-label="{dismiss_label}"').tooltip(
            dismiss_label
        )


def _render_planned_section(rows: list[RadarPlannedRow]) -> None:
    with ui.card().classes(SECTION_CARD):
        with ui.row().classes("w-full items-center justify-between gap-4"):
            with ui.column().classes("gap-0"):
                ui.label(t("unplanned_radar.planned_heading")).classes(SECTION_HEADING)
                ui.label(t("unplanned_radar.planned_hint")).classes(BODY_MUTED)
            ui.button(
                t("unplanned_radar.view_calendar"),
                icon="calendar_month",
                on_click=lambda: ui.navigate.to(_PAYMENT_CALENDAR_URL),
            ).props("flat color=primary size=sm")
        if not rows:
            ui.label(t("unplanned_radar.planned_empty")).classes(f"{BODY_MUTED} mt-2")
            return
        for row in rows:
            with ui.row().classes("w-full items-center gap-3 py-2 border-b border-slate-100"):
                ui.icon("event_repeat", size="1.3rem").classes("text-primary")
                with ui.column().classes("flex-1 gap-0"):
                    ui.label(row.name).classes("text-sm font-medium")
                    ui.label(t("unplanned_radar.planned_linked", count=row.linked_count)).classes(
                        "text-xs text-slate-500"
                    )
                    ui.label(
                        t(
                            "unplanned_radar.occurrence_dates",
                            dates=", ".join(_fmt_date(d) for d in row.linked_dates),
                        )
                    ).classes("text-xs text-slate-400")
                ui.label(cadence_label(row.frequency, row.interval)).classes(
                    "text-xs text-slate-500 w-40 text-right"
                )
                ui.label(
                    t("unplanned_radar.planned_starts", date=_fmt_date(row.start_date))
                ).classes("text-xs text-slate-500 w-40 text-right")
                ui.label(_fmt_amount(row.amount)).classes(
                    f"{AMOUNT_EXPENSE} text-sm w-24 text-right"
                )


async def _dismiss(candidate: RadarCandidate) -> None:
    async def _do(session: Any) -> None:
        await UnplannedRadarService(session).dismiss(candidate)

    try:
        await with_session(_do)
    except KaletaError as exc:
        notify_kaleta_error(exc)
        return
    ui.notify(t("unplanned_radar.dismissed_msg"), type="info")
    ui.navigate.reload()


def _build_plan_dialog(
    *,
    account_opts: dict[int, str],
    category_opts: dict[int, str],
) -> Callable[[RadarCandidate], None]:
    """Build the pre-filled "plan this cost" dialog; returns its opener."""
    pending: dict[str, RadarCandidate | None] = {"candidate": None}

    with ui.dialog() as dialog, ui.card().classes("w-[520px] gap-3"):
        ui.label(t("unplanned_radar.dialog_title")).classes("text-lg font-bold")
        hint = ui.label("").classes(BODY_MUTED)
        name_in = (
            ui.input(label=t("unplanned_radar.field_name"))
            .props("dense outlined")
            .classes("w-full")
        )
        with ui.row().classes("w-full gap-2"):
            amount_in = (
                ui.number(
                    label=t("unplanned_radar.field_amount"),
                    value=0,
                    min=0,
                    format="%.2f",
                )
                .props("dense outlined")
                .classes("flex-1")
            )
            start_in = (
                ui.input(label=t("unplanned_radar.field_start"))
                .props("dense outlined type=date")
                .classes("flex-1")
            )
        account_in = (
            ui.select(options=account_opts, label=t("unplanned_radar.field_account"))
            .props("dense outlined")
            .classes("w-full")
        )
        category_in = (
            ui.select(
                options=category_opts,
                label=t("unplanned_radar.field_category"),
                with_input=True,
            )
            .props("dense outlined clearable")
            .classes("w-full")
        )
        frequency_label = ui.label("").classes(BODY_MUTED)
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            save_btn = ui.button(t("unplanned_radar.plan_it"), icon="check").props(
                "color=primary unelevated"
            )

    def open_dialog(candidate: RadarCandidate) -> None:
        if not account_opts:
            ui.notify(t("unplanned_radar.no_account"), type="warning")
            return
        pending["candidate"] = candidate
        hint.set_text(t("unplanned_radar.dialog_hint", count=candidate.occurrences))
        name_in.set_value(candidate.source_name)
        amount_in.set_value(float(candidate.typical_amount))
        start_in.set_value(candidate.next_expected_at.isoformat())
        account_in.set_value(candidate.account_id if candidate.account_id in account_opts else None)
        category_in.set_value(
            candidate.category_id if candidate.category_id in category_opts else None
        )
        frequency_label.set_text(
            t(
                "unplanned_radar.field_frequency_value",
                label=t("unplanned_radar.field_frequency"),
                value=cadence_label(candidate.frequency, candidate.interval),
            )
        )
        dialog.open()

    async def save() -> None:
        candidate = pending["candidate"]
        if candidate is None:
            return
        name = (name_in.value or "").strip()
        try:
            amount = Decimal(str(amount_in.value or 0)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError, TypeError):
            ui.notify(t("unplanned_radar.invalid_amount"), type="warning")
            return
        try:
            start_date = (
                datetime.date.fromisoformat(start_in.value)
                if start_in.value
                else candidate.next_expected_at
            )
        except ValueError:
            ui.notify(t("unplanned_radar.invalid_start"), type="warning")
            return
        account_id = int(account_in.value) if account_in.value is not None else None
        category_id = int(category_in.value) if category_in.value is not None else None

        async def _do(session: Any) -> None:
            await UnplannedRadarService(session).create_planned_from_candidate(
                candidate,
                account_id=account_id,
                category_id=category_id,
                amount=amount,
                start_date=start_date,
                name=name,
            )

        try:
            await with_session(_do)
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return
        dialog.close()
        ui.notify(t("unplanned_radar.created", name=name), type="positive")
        ui.navigate.reload()

    save_btn.on_click(save)
    return open_dialog
