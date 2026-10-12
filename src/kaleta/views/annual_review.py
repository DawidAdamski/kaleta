# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/wizard/annual-review?year=``: close a year and set up the next.

``budgets-annual-review`` (``KAL-ANR-001``…``003``). Three steps on one page:
the year's plan against its spending, the carry of its budgets into the next
year with a % per category (confirmed as a diff, applied through the yearly
plan), and the commitments — subscriptions and irregular-fund items — each
kept, adjusted or dropped.
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.schemas.annual_review import AnnualCarry, AnnualSummary, Commitment
from kaleta.schemas.yearly_plan import BudgetDiff, YearlyPlanPayload
from kaleta.services import AnnualReviewService, YearlyPlanService, with_session
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.layout import page_layout
from kaleta.views.theme import BODY_MUTED, PAGE_TITLE, SECTION_CARD, SECTION_HEADING

REVIEW_URL = "/wizard/annual-review"
#: Years the selector offers before the current one.
YEARS_BACK = 5
#: A category can go down to nothing, not below.
MIN_PCT = Decimal("-100")


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def register() -> None:
    @ui.page(REVIEW_URL)
    async def annual_review_page(year: int | None = None) -> None:
        this_year = datetime.date.today().year
        oldest = this_year - YEARS_BACK
        chosen = year if year is not None and oldest <= year <= this_year else this_year
        with page_layout(t("annual_review.title"), wide=True):
            with ui.row().classes("w-full items-end justify-between gap-4"):
                with ui.column().classes("gap-1"):
                    ui.label(t("annual_review.title")).classes(PAGE_TITLE)
                    ui.label(t("annual_review.subtitle", year=chosen, next=chosen + 1)).classes(
                        BODY_MUTED
                    )
                ui.select(
                    {y: str(y) for y in range(this_year, this_year - YEARS_BACK - 1, -1)},
                    value=chosen,
                    label=t("annual_review.year"),
                    on_change=lambda e: ui.navigate.to(f"{REVIEW_URL}?year={e.value}"),
                ).classes("w-32")
            await _Review(chosen).render()


class _Review:
    def __init__(self, year: int) -> None:
        self.year = year
        self.adjustments: dict[int, Decimal] = {}
        self.payload: YearlyPlanPayload | None = None

    async def render(self) -> None:
        self._build_diff_dialog()
        self._build_adjust_dialog()
        await self.summary()
        await self.carry()
        await self.commitments()

    # ── Step 1 ────────────────────────────────────────────────────────────

    @ui.refreshable_method
    async def summary(self) -> None:
        async def _load(session: Any) -> AnnualSummary:
            return await AnnualReviewService(session).summary(self.year)

        data = await with_session(_load)
        with ui.card().classes(SECTION_CARD):
            ui.label(t("annual_review.step_summary", year=self.year)).classes(SECTION_HEADING)
            if not data.rows:
                ui.label(t("annual_review.summary_empty")).classes(BODY_MUTED)
                return
            self._header(
                t("common.category"),
                t("annual_review.planned"),
                t("annual_review.actual"),
                t("annual_review.difference"),
            )
            for row in data.rows:
                with (
                    ui.row()
                    .classes("w-full px-2 py-1 items-center border-b")
                    .props(f'data-testid="anr-summary-{row.category_id}"')
                ):
                    ui.label(row.name).classes("flex-1")
                    ui.label(_fmt(row.planned)).classes("w-32 text-right k-mono")
                    ui.label(_fmt(row.actual)).classes("w-32 text-right k-mono")
                    tone = "text-negative" if row.difference < 0 else ""
                    ui.label(_fmt(row.difference)).classes(f"w-32 text-right k-mono {tone}")
            with ui.row().classes("w-full px-2 pt-2 items-center font-semibold"):
                ui.label(t("common.total")).classes("flex-1")
                ui.label(_fmt(data.planned_total)).classes("w-32 text-right k-mono").props(
                    'data-testid="anr-planned-total"'
                )
                ui.label(_fmt(data.actual_total)).classes("w-32 text-right k-mono").props(
                    'data-testid="anr-actual-total"'
                )
                ui.label(_fmt(data.planned_total - data.actual_total)).classes(
                    "w-32 text-right k-mono"
                )

    @staticmethod
    def _header(*labels: str) -> None:
        with ui.row().classes(f"w-full px-2 text-xs font-medium border-b {BODY_MUTED}"):
            first, *rest = labels
            ui.label(first).classes("flex-1")
            for label in rest:
                ui.label(label).classes("w-32 text-right")

    # ── Step 2 ────────────────────────────────────────────────────────────

    @ui.refreshable_method
    async def carry(self) -> None:
        async def _load(session: Any) -> AnnualCarry:
            return await AnnualReviewService(session).carry(self.year, self.adjustments)

        data = await with_session(_load)
        self.payload = data.payload
        with ui.card().classes(SECTION_CARD):
            ui.label(t("annual_review.step_carry", next=self.year + 1)).classes(SECTION_HEADING)
            if not data.rows:
                ui.label(t("annual_review.carry_empty", year=self.year)).classes(BODY_MUTED)
                return
            ui.label(t("annual_review.carry_hint")).classes(f"{BODY_MUTED} text-sm")
            self._header(
                t("common.category"),
                t("annual_review.planned_this", year=self.year),
                t("annual_review.adjustment"),
                t("annual_review.planned_next", year=self.year + 1),
            )
            for row in data.rows:
                with (
                    ui.row()
                    .classes("w-full px-2 py-1 items-center border-b")
                    .props(f'data-testid="anr-carry-{row.category_id}"')
                ):
                    ui.label(row.name).classes("flex-1")
                    ui.label(_fmt(row.planned)).classes("w-32 text-right k-mono")
                    # Applied on leaving the field (or Enter), not per keystroke:
                    # the redraw would rebuild the input being typed in.
                    pct_in = (
                        ui.number(value=float(row.pct), step=1, min=-100, suffix="%")
                        .props(f'dense data-testid="anr-pct-{row.category_id}"')
                        .classes("w-32 text-right")
                    )
                    for event in ("blur", "keydown.enter"):
                        pct_in.on(
                            event,
                            lambda _e, cid=row.category_id, w=pct_in: self._set_pct(cid, w.value),
                        )
                    ui.label(_fmt(row.next_amount)).classes(
                        "w-32 text-right k-mono font-semibold"
                    ).props(f'data-testid="anr-next-{row.category_id}"')
            if data.replaces_plan:
                ui.label(t("annual_review.replaces_plan", next=self.year + 1)).classes(
                    "text-sm text-warning mt-2"
                )
            with ui.row().classes("w-full justify-end mt-2"):
                ui.button(
                    t("annual_review.carry_button", next=self.year + 1),
                    icon="east",
                    on_click=self._review_diff,
                ).props("color=primary no-caps")

    def _set_pct(self, category_id: int, value: Any) -> None:
        pct = _decimal(value or 0)
        if pct is None:
            return
        pct = max(pct, MIN_PCT)
        if self.adjustments.get(category_id, Decimal("0")) == pct:
            return  # nothing changed: no redraw
        self.adjustments[category_id] = pct
        self.carry.refresh()

    def _build_diff_dialog(self) -> None:
        self.diff_dialog = ui.dialog()
        with self.diff_dialog, ui.card().classes("w-[560px] gap-2"):
            ui.label(t("budget_builder.diff_title")).classes("text-lg font-bold")
            self.diff_summary = ui.label("").classes(BODY_MUTED)
            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=self.diff_dialog.close).props("flat")
                ui.button(
                    t("budget_builder.apply_confirm"), icon="check", on_click=self._apply
                ).props("color=primary unelevated")

    async def _review_diff(self) -> None:
        payload = self.payload
        if payload is None:
            return

        async def _diff(session: Any) -> BudgetDiff:
            return await YearlyPlanService(session).diff(payload)

        diff = await with_session(_diff)
        if not diff.added and not diff.updated:
            ui.notify(t("budget_builder.nothing_to_change"), type="info")
            return
        self.diff_summary.set_text(
            t(
                "budget_builder.diff_summary",
                added=len(diff.added),
                updated=len(diff.updated),
                unchanged=diff.unchanged_count,
            )
        )
        self.diff_dialog.open()

    async def _apply(self) -> None:
        payload = self.payload
        if payload is None:
            return

        async def _write(session: Any) -> None:
            await YearlyPlanService(session).apply(payload)

        try:
            await with_session(_write)
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return
        self.diff_dialog.close()
        ui.notify(t("annual_review.carried", next=payload.year), type="positive")
        self.carry.refresh()

    # ── Step 3 ────────────────────────────────────────────────────────────

    @ui.refreshable_method
    async def commitments(self) -> None:
        async def _load(session: Any) -> list[Commitment]:
            return await AnnualReviewService(session).commitments()

        rows = await with_session(_load)
        with ui.card().classes(SECTION_CARD):
            ui.label(t("annual_review.step_commitments")).classes(SECTION_HEADING)
            if not rows:
                ui.label(t("annual_review.commitments_empty")).classes(BODY_MUTED)
                return
            ui.label(t("annual_review.commitments_hint")).classes(f"{BODY_MUTED} text-sm")
            for row in rows:
                with (
                    ui.row()
                    .classes("w-full px-2 py-1 items-center gap-3 border-b")
                    .props(f'data-testid="anr-commitment-{row.kind.value}-{row.id}"')
                ):
                    ui.label(row.name).classes("flex-1")
                    ui.label(t(f"annual_review.kind_{row.kind.value}")).classes(
                        f"w-40 text-sm {BODY_MUTED}"
                    )
                    ui.label(t("annual_review.per_year", amount=_fmt(row.yearly))).classes(
                        "w-36 text-right k-mono"
                    )
                    kept = ui.label(t("annual_review.kept")).classes("text-positive text-sm")
                    kept.set_visibility(False)
                    with ui.row().classes("gap-1 no-wrap"):
                        ui.button(
                            t("annual_review.keep"),
                            on_click=lambda _e, k=kept: k.set_visibility(True),
                        ).props("flat dense no-caps")
                        ui.button(
                            t("annual_review.adjust"),
                            on_click=lambda _e, r=row: self._open_adjust(r),
                        ).props("flat dense no-caps color=primary")
                        ui.button(
                            t("annual_review.drop"), on_click=lambda _e, r=row: self._drop(r)
                        ).props("flat dense no-caps color=negative")

    def _build_adjust_dialog(self) -> None:
        self.adjusting: Commitment | None = None
        self.adjust_dialog = ui.dialog()
        with self.adjust_dialog, ui.card().classes("w-[380px] gap-3"):
            self.adjust_title = ui.label("").classes("text-lg font-semibold")
            self.adjust_amount = ui.number(
                t("annual_review.new_amount"), min=0, step=1, format="%.2f"
            ).classes("w-full")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("common.cancel"), on_click=self.adjust_dialog.close).props("flat")
                ui.button(t("common.save"), on_click=self._save_adjust).props("color=primary")

    def _open_adjust(self, row: Commitment) -> None:
        self.adjusting = row
        self.adjust_title.set_text(t(f"annual_review.adjust_{row.kind.value}", name=row.name))
        self.adjust_amount.set_value(float(row.amount))
        self.adjust_dialog.open()

    async def _save_adjust(self) -> None:
        row = self.adjusting
        amount = _decimal(self.adjust_amount.value)
        if row is None or amount is None or amount <= 0:
            ui.notify(t("annual_review.amount_needed"), type="negative")
            return

        async def _write(session: Any) -> None:
            await AnnualReviewService(session).adjust(row.kind, row.id, amount)

        try:
            await with_session(_write)
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return
        self.adjust_dialog.close()
        ui.notify(t("annual_review.adjusted", name=row.name), type="positive")
        self.commitments.refresh()

    async def _drop(self, row: Commitment) -> None:
        async def _write(session: Any) -> None:
            await AnnualReviewService(session).drop(row.kind, row.id)

        try:
            await with_session(_write)
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return
        ui.notify(t("annual_review.dropped", name=row.name), type="positive")
        self.commitments.refresh()
