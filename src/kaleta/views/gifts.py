# SPDX-License-Identifier: AGPL-3.0-or-later
"""The gift grid: people down the side, occasions across, one grid per year.

Typing an amount saves that cell and updates the totals in place, without
redrawing the grid, so Tab carries on to the next cell. Anything that changes
the grid's shape (a person, an occasion, a copied year, a bought mark) reloads
the page.
"""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from nicegui import ui
from pydantic import ValidationError

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.schemas.gift import (
    GIFT_NAME_MAX,
    GIFT_NOTE_MAX,
    GiftCellResponse,
    GiftCellSet,
    GiftGrid,
    GiftLaneResponse,
    GiftName,
)
from kaleta.services import GiftService, with_session
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.layout import page_layout
from kaleta.views.theme import BODY_MUTED, PAGE_TITLE, SECTION_CARD

GIFTS_URL = "/wizard/gifts"

#: The columns a new user starts with, in order (``gifts.default_occasions.*``).
DEFAULT_OCCASION_KEYS = ("birthday", "name_day", "christmas", "easter", "st_nicholas", "other")

_GRID_CSS = """
.k-gift-scroll{width:100%;overflow-x:auto}
.k-gift-grid{border-collapse:separate;border-spacing:0;min-width:100%}
.k-gift-grid th,.k-gift-grid td{padding:4px 8px;border-bottom:1px solid var(--k-hairline);
  white-space:nowrap;text-align:right}
.k-gift-grid thead th{font-weight:600;color:var(--k-muted-strong)}
.k-gift-grid .k-gift-person{position:sticky;left:0;z-index:1;text-align:left;
  background:var(--k-surface)}
.k-gift-grid tfoot th,.k-gift-grid tfoot td,.k-gift-grid .k-gift-total{font-weight:700}
.k-gift-grid .k-gift-cell{min-width:7.5rem}
.k-gift-grid .k-gift-cell input{text-align:right;font-variant-numeric:tabular-nums}
.k-gift-grid .k-gift-bought{color:var(--k-accent-text);font-size:12px}
"""


def _fmt_amount(d: Decimal) -> str:
    return f"{d:,.2f}"


def _to_amount(value: float | int | str | None) -> Decimal | None:
    """A number input's value as a stored amount; blank means no cell."""
    if value is None or value == "":
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"))


class GiftGridPage:
    """One year's grid and the dialogs around it."""

    def __init__(self, grid: GiftGrid, buyable: list[tuple[int, str]]) -> None:
        self.grid = grid
        self.year = grid.year
        self.buyable = buyable
        self.cells: dict[tuple[int, int], GiftCellResponse] = {
            (c.person_id, c.occasion_id): c for c in grid.cells
        }
        self.people = {p.id: p for p in grid.people}
        self.occasions = {o.id: o for o in grid.occasions}
        self.row_labels: dict[int, ui.label] = {}
        self.column_labels: dict[int, ui.label] = {}
        self.total_labels: list[ui.label] = []

    # ── Plumbing ───────────────────────────────────────────────────────────

    def _reload(self, year: int | None = None) -> None:
        ui.navigate.to(f"{GIFTS_URL}?year={year if year is not None else self.year}")

    async def _run(self, action: Callable[[GiftService], Awaitable[Any]]) -> bool:
        """Run one service call; a domain error becomes a toast and ``False``."""

        async def _call(session: Any) -> Any:
            return await action(GiftService(session))

        try:
            await with_session(_call)
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return False
        return True

    # ── Page ───────────────────────────────────────────────────────────────

    def render(self) -> None:
        ui.add_css(_GRID_CSS)
        self._header()
        self._toolbar()
        if not self.grid.cells and self.grid.previous_year_has_cells:
            self._copy_banner()
        if not self.grid.people:
            # The columns still show, so a new user sees the occasions to fill.
            ui.label(t("gifts.empty_people")).classes(f"{BODY_MUTED} mt-4")
        with (
            ui.card().classes(f"{SECTION_CARD} w-full p-0 mt-2"),
            ui.element("div").classes("k-gift-scroll"),
        ):
            self._table()

    def _header(self) -> None:
        with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label(t("gifts.title")).classes(PAGE_TITLE)
                ui.label(t("gifts.subtitle")).classes(BODY_MUTED)
            with ui.row().classes("items-center gap-4"):
                with ui.row().classes("items-center gap-1"):
                    ui.button(
                        icon="chevron_left", on_click=lambda: self._reload(self.year - 1)
                    ).props(f'flat dense round aria-label="{t("gifts.previous_year")}"')
                    ui.label(str(self.year)).classes("text-lg font-semibold tabular-nums")
                    ui.button(
                        icon="chevron_right", on_click=lambda: self._reload(self.year + 1)
                    ).props(f'flat dense round aria-label="{t("gifts.next_year")}"')
                with ui.column().classes("gap-0 items-end"):
                    ui.label(t("gifts.yearly_total", year=self.year)).classes(
                        f"{BODY_MUTED} text-xs"
                    )
                    total = ui.label(_fmt_amount(self.grid.total)).classes("text-lg font-bold")
                    total.props('data-testid="gift-total"')
                    self.total_labels.append(total)

    def _toolbar(self) -> None:
        with ui.row().classes("w-full items-end gap-3 flex-wrap mt-2"):
            for label_key, button_key, add in (
                ("gifts.new_person", "gifts.add_person", self._add_person),
                ("gifts.new_occasion", "gifts.add_occasion", self._add_occasion),
            ):
                field = (
                    ui.input(label=t(label_key))
                    .props(f"dense outlined maxlength={GIFT_NAME_MAX}")
                    .classes("w-48")
                )

                async def _submit(_e: Any = None, f: ui.input = field, fn: Any = add) -> None:
                    await fn((f.value or "").strip())

                field.on("keydown.enter", _submit)
                ui.button(t(button_key), icon="add", on_click=_submit).props(
                    "unelevated no-caps color=primary"
                )

    def _copy_banner(self) -> None:
        with ui.row().classes("w-full items-center gap-3 mt-2"):
            ui.label(t("gifts.empty_year", year=self.year)).classes(BODY_MUTED)
            ui.button(
                t("gifts.copy_from", year=self.year - 1),
                icon="content_copy",
                on_click=self._copy_previous,
            ).props("flat no-caps color=primary")

    def _table(self) -> None:
        occasions = self.grid.occasions
        with ui.element("table").classes("k-gift-grid"):
            with ui.element("thead"), ui.element("tr"):
                with ui.element("th").classes("k-gift-person"):
                    ui.label(t("gifts.person_col"))
                for index, occasion in enumerate(occasions):
                    with (
                        ui.element("th"),
                        ui.row().classes("items-center justify-end gap-0 no-wrap"),
                    ):
                        ui.label(occasion.name)
                        self._lane_menu(occasion, index, len(occasions), column=True)
                with ui.element("th").classes("k-gift-total"):
                    ui.label(t("gifts.total_col"))

            with ui.element("tbody"):
                for index, person in enumerate(self.grid.people):
                    with ui.element("tr").props(f'data-testid="gift-row-{person.id}"'):
                        with (
                            ui.element("th").classes("k-gift-person"),
                            ui.row().classes("items-center gap-0 no-wrap"),
                        ):
                            ui.label(person.name)
                            self._lane_menu(person, index, len(self.grid.people), column=False)
                        for occasion in occasions:
                            with ui.element("td").classes("k-gift-cell"):
                                self._cell(person, occasion)
                        with ui.element("td").classes("k-gift-total"):
                            label = ui.label(
                                _fmt_amount(self.grid.row_totals.get(person.id, Decimal("0")))
                            ).props(f'data-testid="gift-row-total-{person.id}"')
                            self.row_labels[person.id] = label

            with ui.element("tfoot"), ui.element("tr"):
                with ui.element("th").classes("k-gift-person"):
                    ui.label(t("gifts.total_col"))
                for occasion in occasions:
                    with ui.element("td"):
                        label = ui.label(
                            _fmt_amount(self.grid.column_totals.get(occasion.id, Decimal("0")))
                        ).props(f'data-testid="gift-col-total-{occasion.id}"')
                        self.column_labels[occasion.id] = label
                with ui.element("td"):
                    total = ui.label(_fmt_amount(self.grid.total)).props(
                        'data-testid="gift-grid-total"'
                    )
                    self.total_labels.append(total)

    # ── Cells ──────────────────────────────────────────────────────────────

    def _cell(self, person: GiftLaneResponse, occasion: GiftLaneResponse) -> None:
        cell = self.cells.get((person.id, occasion.id))
        name = t("gifts.cell_label", person=person.name, occasion=occasion.name)
        with ui.row().classes("items-center justify-end gap-0 no-wrap"):
            field = (
                ui.number(
                    value=float(cell.amount) if cell is not None else None,
                    min=0,
                    format="%.2f",
                    on_change=lambda e, p=person.id, o=occasion.id: self._save_amount(
                        p, o, e.value
                    ),
                )
                .props(f'dense borderless aria-label="{name}"')
                .classes("w-24")
            )
            field.props(f'data-testid="gift-cell-{person.id}-{occasion.id}"')
            if cell is not None and cell.note:
                field.tooltip(cell.note)
            options = t("gifts.cell_options", person=person.name, occasion=occasion.name)
            with (
                ui.button(icon="more_vert")
                .props(f'flat dense round size=xs aria-label="{options}"')
                .classes("text-[var(--k-muted)]"),
                ui.menu(),
            ):
                ui.menu_item(
                    t("gifts.note"), on_click=lambda p=person, o=occasion: self._open_note(p, o)
                )
                if cell is not None and cell.bought:
                    ui.menu_item(
                        t("gifts.mark_not_bought"),
                        on_click=lambda c=cell: self._mark_not_bought(c.id),
                    )
                else:
                    ui.menu_item(
                        t("gifts.mark_bought"),
                        on_click=lambda p=person, o=occasion: self._open_bought(p, o),
                    )
        if cell is not None and cell.bought and cell.actual_cost is not None:
            ui.label(t("gifts.bought_cost", amount=_fmt_amount(cell.actual_cost))).classes(
                "k-gift-bought"
            ).props(f'data-testid="gift-bought-{cell.id}"')

    async def _save_amount(self, person_id: int, occasion_id: int, value: Any) -> None:
        try:
            payload = GiftCellSet(
                amount=_to_amount(value),
                note=getattr(self.cells.get((person_id, occasion_id)), "note", None),
            )
        except (ValidationError, ArithmeticError, ValueError):
            ui.notify(t("gifts.invalid_amount"), type="warning")
            return
        current = self.cells.get((person_id, occasion_id))
        if (current.amount if current else None) == payload.amount:
            return

        async def _set(svc: GiftService) -> None:
            await svc.set_cell(self.year, person_id, occasion_id, payload)
            self.grid = await svc.grid(self.year)

        if await self._run(_set):
            self._refresh_totals()

    def _refresh_totals(self) -> None:
        """Bring the cells map and every total up to date, without a redraw."""
        self.cells = {(c.person_id, c.occasion_id): c for c in self.grid.cells}
        for person_id, label in self.row_labels.items():
            label.set_text(_fmt_amount(self.grid.row_totals.get(person_id, Decimal("0"))))
        for occasion_id, label in self.column_labels.items():
            label.set_text(_fmt_amount(self.grid.column_totals.get(occasion_id, Decimal("0"))))
        for label in self.total_labels:
            label.set_text(_fmt_amount(self.grid.total))

    def _open_note(self, person: GiftLaneResponse, occasion: GiftLaneResponse) -> None:
        cell = self.cells.get((person.id, occasion.id))
        if cell is None:
            ui.notify(t("gifts.cell_empty"), type="warning")
            return
        with ui.dialog() as dialog, ui.card().classes("w-[420px] gap-3"):
            ui.label(t("gifts.note_title", person=person.name, occasion=occasion.name)).classes(
                "text-lg font-bold"
            )
            note_in = (
                ui.input(label=t("gifts.note"), value=cell.note or "")
                .props(f"dense outlined maxlength={GIFT_NOTE_MAX} autofocus")
                .classes("w-full")
            )

            async def _save() -> None:
                payload = GiftCellSet(amount=cell.amount, note=note_in.value or None)

                async def _set(svc: GiftService) -> None:
                    await svc.set_cell(self.year, person.id, occasion.id, payload)

                if await self._run(_set):
                    dialog.close()
                    ui.notify(t("gifts.note_saved"), type="positive")
                    self._reload()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.save"), icon="check", on_click=_save).props(
                    "color=primary unelevated"
                )
        dialog.open()

    # ── Bought (KAL-GFT-003) ───────────────────────────────────────────────

    def _open_bought(self, person: GiftLaneResponse, occasion: GiftLaneResponse) -> None:
        cell = self.cells.get((person.id, occasion.id))
        if cell is None:
            ui.notify(t("gifts.cell_empty"), type="warning")
            return
        if not self.buyable:
            ui.notify(t("gifts.bought_no_tx"), type="warning")
            return
        with ui.dialog() as dialog, ui.card().classes("w-[460px] gap-3"):
            ui.label(t("gifts.bought_title")).classes("text-lg font-bold")
            ui.label(t("gifts.bought_body")).classes(BODY_MUTED)
            tx_select = (
                ui.select(dict(self.buyable), label=t("gifts.bought_pick"), with_input=True)
                .props("dense outlined")
                .classes("w-full")
            )

            async def _link() -> None:
                if not tx_select.value:
                    ui.notify(t("gifts.bought_pick_required"), type="warning")
                    return
                tx_id = int(tx_select.value)
                if await self._run(lambda svc: svc.link_transaction(cell.id, tx_id)):
                    dialog.close()
                    ui.notify(t("gifts.bought_done"), type="positive")
                    self._reload()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("gifts.bought_confirm"), icon="check", on_click=_link).props(
                    "color=primary unelevated"
                )
        dialog.open()

    async def _mark_not_bought(self, cell_id: int) -> None:
        if await self._run(lambda svc: svc.mark_not_bought(cell_id)):
            ui.notify(t("gifts.not_bought_done"), type="positive")
            self._reload()

    # ── People and occasions ───────────────────────────────────────────────

    async def _add_person(self, name: str) -> None:
        await self._add_lane(name, column=False)

    async def _add_occasion(self, name: str) -> None:
        await self._add_lane(name, column=True)

    async def _add_lane(self, name: str, *, column: bool) -> None:
        try:
            payload = GiftName(name=name)
        except ValidationError:
            ui.notify(t("errors.gift.name_required"), type="warning")
            return

        async def _add(svc: GiftService) -> None:
            if column:
                await svc.add_occasion(payload)
            else:
                await svc.add_person(payload)

        if await self._run(_add):
            self._reload()

    def _lane_menu(self, lane: GiftLaneResponse, index: int, count: int, *, column: bool) -> None:
        back, forward = (
            ("gifts.move_left", "gifts.move_right")
            if column
            else (
                "gifts.move_up",
                "gifts.move_down",
            )
        )
        with (
            ui.button(icon="more_vert")
            .props(
                f'flat dense round size=xs aria-label="{t("gifts.lane_options", name=lane.name)}"'
            )
            .classes("text-[var(--k-muted)]"),
            ui.menu(),
        ):
            ui.menu_item(t("gifts.rename"), on_click=lambda: self._open_rename(lane, column))
            if index > 0:
                ui.menu_item(t(back), on_click=lambda: self._move(lane.id, -1, column))
            if index < count - 1:
                ui.menu_item(t(forward), on_click=lambda: self._move(lane.id, 1, column))
            ui.menu_item(t("gifts.archive"), on_click=lambda: self._open_archive(lane, column))

    async def _move(self, lane_id: int, step: int, column: bool) -> None:
        async def _do(svc: GiftService) -> None:
            if column:
                await svc.move_occasion(lane_id, step)
            else:
                await svc.move_person(lane_id, step)

        if await self._run(_do):
            self._reload()

    def _open_rename(self, lane: GiftLaneResponse, column: bool) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-[420px] gap-3"):
            ui.label(t("gifts.rename")).classes("text-lg font-bold")
            name_in = (
                ui.input(label=t("gifts.name"), value=lane.name)
                .props(f"dense outlined maxlength={GIFT_NAME_MAX} autofocus")
                .classes("w-full")
            )

            async def _save() -> None:
                try:
                    payload = GiftName(name=(name_in.value or "").strip())
                except ValidationError:
                    ui.notify(t("errors.gift.name_required"), type="warning")
                    return

                async def _rename(svc: GiftService) -> None:
                    if column:
                        await svc.rename_occasion(lane.id, payload)
                    else:
                        await svc.rename_person(lane.id, payload)

                if await self._run(_rename):
                    dialog.close()
                    self._reload()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.save"), icon="check", on_click=_save).props(
                    "color=primary unelevated"
                )
        dialog.open()

    def _open_archive(self, lane: GiftLaneResponse, column: bool) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-[440px] gap-3"):
            ui.label(t("gifts.archive_title", name=lane.name)).classes("text-lg font-bold")
            ui.label(t("gifts.archive_body", name=lane.name)).classes(BODY_MUTED)

            async def _archive() -> None:
                async def _do(svc: GiftService) -> None:
                    if column:
                        await svc.archive_occasion(lane.id)
                    else:
                        await svc.archive_person(lane.id)

                if await self._run(_do):
                    dialog.close()
                    self._reload()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("gifts.archive_confirm"), icon="delete", on_click=_archive).props(
                    "color=negative unelevated"
                )
        dialog.open()

    async def _copy_previous(self) -> None:
        source = self.year - 1
        copied: dict[str, int] = {}

        async def _copy(svc: GiftService) -> None:
            copied["count"] = await svc.copy_year(source, self.year)

        if await self._run(_copy):
            ui.notify(t("gifts.copied", count=copied["count"], year=source), type="positive")
            self._reload()


def register() -> None:
    @ui.page(GIFTS_URL)
    async def gifts_page(year: int | None = None) -> None:
        shown_year = year if year is not None else datetime.date.today().year
        defaults = [t(f"gifts.default_occasions.{key}") for key in DEFAULT_OCCASION_KEYS]

        async def _load(session: Any) -> tuple[GiftGrid, list[tuple[int, str]]]:
            svc = GiftService(session)
            await svc.ensure_default_occasions(defaults)
            grid = await svc.grid(shown_year)
            buyable = [
                (
                    tx.id,
                    f"{tx.date.isoformat()} · {tx.description or '—'} · {_fmt_amount(tx.amount)}",
                )
                for tx in await svc.buyable_transactions(limit=50)
            ]
            return grid, buyable

        grid, buyable = await with_session(_load)
        with page_layout(t("gifts.title"), wide=True):
            GiftGridPage(grid, buyable).render()
