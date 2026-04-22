from __future__ import annotations

import calendar
import datetime
from decimal import Decimal

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.schemas.monthly_readiness import (
    Stage1CloseLastMonth,
    Stage2ConfirmIncome,
    Stage3AllocateNewMonth,
    Stage4AcknowledgeBills,
    Stage4PlannedRow,
)
from kaleta.services import MonthlyReadinessService
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    BODY_MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)


def _fmt(d: Decimal) -> str:
    return f"{d:,.2f}"


def _month_label(year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"


def register() -> None:
    @ui.page("/wizard/monthly-readiness")
    async def monthly_readiness_page() -> None:
        today = datetime.date.today()
        state = {"year": today.year, "month": today.month}

        async with AsyncSessionFactory() as session:
            svc = MonthlyReadinessService(session)
            row = await svc.get_or_create(state["year"], state["month"])
            stage_1 = await svc.stage_1(state["year"], state["month"])
            stage_2 = await svc.stage_2(state["year"], state["month"])
            stage_3 = await svc.stage_3(state["year"], state["month"])
            stage_4 = await svc.stage_4(state["year"], state["month"])

        stages_done = {
            1: row.stage_1_done,
            2: row.stage_2_done,
            3: row.stage_3_done,
            4: row.stage_4_done,
        }

        with page_layout(t("monthly_readiness.title"), wide=True):
            # ── Header ───────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                with ui.column().classes("gap-1"):
                    ui.label(t("monthly_readiness.title")).classes(PAGE_TITLE)
                    ui.label(
                        t(
                            "monthly_readiness.subtitle",
                            month=_month_label(state["year"], state["month"]),
                        )
                    ).classes(BODY_MUTED)
                n_done = sum(1 for v in stages_done.values() if v)
                ui.badge(
                    t("monthly_readiness.progress", done=n_done, total=4),
                    color="positive" if n_done == 4 else "primary",
                ).classes("text-sm px-3 py-1")

            # ── Stage 1: Close last month ────────────────────────────────
            _render_stage_1(stage_1, stages_done[1], state)

            # ── Stage 2: Confirm income ──────────────────────────────────
            _render_stage_2(stage_2, stages_done[2], state)

            # ── Stage 3: Allocate new month ──────────────────────────────
            _render_stage_3(stage_3, stages_done[3], state)

            # ── Stage 4: Acknowledge bills ───────────────────────────────
            _render_stage_4(stage_4, stages_done[4], state, row.seen_planned_ids)

            # ── Overall ready badge ──────────────────────────────────────
            with ui.card().classes(SECTION_CARD):
                if all(stages_done.values()):
                    with ui.row().classes("items-center gap-3"):
                        ui.icon("check_circle", size="1.8rem").classes("text-positive")
                        ui.label(t("monthly_readiness.ready")).classes(SECTION_HEADING)
                else:
                    ui.label(t("monthly_readiness.not_ready_hint")).classes(BODY_MUTED)


def _stage_header(num: int, title_key: str, done: bool) -> None:
    icon = "check_circle" if done else "radio_button_unchecked"
    colour = "text-positive" if done else "text-slate-400"
    with ui.row().classes("items-center gap-3"):
        ui.icon(icon, size="1.4rem").classes(colour)
        ui.label(t("monthly_readiness.stage_num", n=num)).classes(
            "text-xs uppercase tracking-wide text-slate-500 font-semibold"
        )
        ui.label(t(title_key)).classes(SECTION_HEADING)


async def _mark_stage(year: int, month: int, stage: int, done: bool = True) -> None:
    async with AsyncSessionFactory() as session:
        await MonthlyReadinessService(session).mark_stage(year, month, stage, done=done)


def _render_stage_1(data: Stage1CloseLastMonth, done: bool, state: dict[str, int]) -> None:
    with ui.card().classes(SECTION_CARD):
        _stage_header(1, "monthly_readiness.stage_1_title", done)
        ui.label(
            t(
                "monthly_readiness.stage_1_body",
                month=_month_label(data.last_year, data.last_month),
                count=data.uncategorised_count,
            )
        ).classes(f"{BODY_MUTED} mt-2")
        with ui.row().classes("items-center gap-2 mt-2"):
            if data.uncategorised_count > 0:
                ui.button(
                    t("monthly_readiness.stage_1_review"),
                    icon="open_in_new",
                    on_click=lambda: ui.navigate.to("/transactions"),
                ).props("flat color=primary size=sm")
            btn_label = (
                t("monthly_readiness.stage_undo")
                if done
                else t("monthly_readiness.stage_1_complete")
            )

            async def _toggle() -> None:
                await _mark_stage(state["year"], state["month"], 1, not done)
                ui.navigate.reload()

            ui.button(
                btn_label,
                icon="check" if not done else "undo",
                on_click=_toggle,
            ).props(
                "color=primary unelevated size=sm"
                if not done
                else "flat color=grey-7 size=sm"
            )


def _render_stage_2(data: Stage2ConfirmIncome, done: bool, state: dict[str, int]) -> None:
    with ui.card().classes(SECTION_CARD):
        _stage_header(2, "monthly_readiness.stage_2_title", done)
        if not data.rows:
            ui.label(t("monthly_readiness.stage_2_no_income")).classes(f"{BODY_MUTED} mt-2")
        else:
            with ui.column().classes("w-full gap-1 mt-2"):
                for r in data.rows:
                    with ui.row().classes("w-full items-center"):
                        ui.label(r.name).classes("flex-1 text-sm")
                        ui.label(_fmt(r.expected)).classes("w-32 text-right text-sm")
                        ui.label(_fmt(r.actual)).classes(
                            "w-32 text-right text-sm "
                            + (AMOUNT_INCOME if r.actual >= r.expected else AMOUNT_EXPENSE)
                        )
        with ui.row().classes("items-center gap-2 mt-3"):
            btn_label = (
                t("monthly_readiness.stage_undo")
                if done
                else t("monthly_readiness.stage_2_complete")
            )

            async def _toggle() -> None:
                await _mark_stage(state["year"], state["month"], 2, not done)
                ui.navigate.reload()

            ui.button(
                btn_label,
                icon="check" if not done else "undo",
                on_click=_toggle,
            ).props(
                "color=primary unelevated size=sm"
                if not done
                else "flat color=grey-7 size=sm"
            )


def _render_stage_3(data: Stage3AllocateNewMonth, done: bool, state: dict[str, int]) -> None:
    with ui.card().classes(SECTION_CARD):
        _stage_header(3, "monthly_readiness.stage_3_title", done)
        ui.label(
            t(
                "monthly_readiness.stage_3_body",
                from_month=_month_label(data.from_year, data.from_month),
                to_month=_month_label(data.to_year, data.to_month),
                new=data.new_count,
                skipped=data.skipped_count,
            )
        ).classes(f"{BODY_MUTED} mt-2")
        with ui.row().classes("items-center gap-2 mt-3"):
            if data.new_count > 0 and not done:

                async def _apply() -> None:
                    async with AsyncSessionFactory() as session:
                        written = await MonthlyReadinessService(session).apply_stage_3(
                            state["year"], state["month"]
                        )
                    ui.notify(
                        t("monthly_readiness.stage_3_applied", count=written),
                        type="positive",
                    )
                    await _mark_stage(state["year"], state["month"], 3, True)
                    ui.navigate.reload()

                ui.button(
                    t("monthly_readiness.stage_3_copy"),
                    icon="content_copy",
                    on_click=_apply,
                ).props("color=primary unelevated size=sm")

            btn_label = (
                t("monthly_readiness.stage_undo")
                if done
                else t("monthly_readiness.stage_3_complete")
            )

            async def _toggle() -> None:
                await _mark_stage(state["year"], state["month"], 3, not done)
                ui.navigate.reload()

            ui.button(
                btn_label,
                icon="check" if not done else "undo",
                on_click=_toggle,
            ).props(
                "flat color=grey-7 size=sm"
                if done
                else "flat color=primary size=sm"
            )


def _render_stage_4(
    data: Stage4AcknowledgeBills, done: bool, state: dict[str, int], _seen_json: str
) -> None:
    with ui.card().classes(SECTION_CARD):
        _stage_header(4, "monthly_readiness.stage_4_title", done)
        if not data.rows:
            ui.label(t("monthly_readiness.stage_4_no_bills")).classes(f"{BODY_MUTED} mt-2")
        else:
            with ui.column().classes("w-full gap-1 mt-2"):
                for r in data.rows:
                    _render_stage_4_row(r, state)
        with ui.row().classes("items-center gap-2 mt-3"):
            btn_label = (
                t("monthly_readiness.stage_undo")
                if done
                else t("monthly_readiness.stage_4_complete")
            )

            async def _toggle() -> None:
                await _mark_stage(state["year"], state["month"], 4, not done)
                ui.navigate.reload()

            ui.button(
                btn_label,
                icon="check" if not done else "undo",
                on_click=_toggle,
            ).props(
                "color=primary unelevated size=sm"
                if not done
                else "flat color=grey-7 size=sm"
            )


def _render_stage_4_row(r: Stage4PlannedRow, state: dict[str, int]) -> None:
    with ui.row().classes("w-full items-center gap-3"):
        cb = ui.checkbox(value=r.seen).props("dense")

        async def _on_change(
            _e: object, pid: int = r.planned_id, ctrl: ui.checkbox = cb
        ) -> None:
            async with AsyncSessionFactory() as session:
                await MonthlyReadinessService(session).set_seen(
                    state["year"], state["month"], pid, seen=bool(ctrl.value)
                )

        cb.on("update:model-value", _on_change)
        ui.label(r.date.strftime("%d.%m")).classes("w-16 text-xs text-slate-500")
        ui.label(r.name).classes("flex-1 text-sm")
        ui.label(r.account_name).classes("w-40 text-xs text-slate-500")
        ui.label(_fmt(r.amount)).classes(f"w-24 text-right text-sm {AMOUNT_EXPENSE}")
