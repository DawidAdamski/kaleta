# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/wizard/safety-funds/{fund_id}``: an irregular-expenses fund's plan.

``funds-irregular-items`` (``KAL-IRR-001``…``003``). The yearly costs the fund
saves for, each at a tenth a month, their total, and the proposal that turns
the total into a monthly planned transfer into the fund's account.
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.schemas.category import CategoryType
from kaleta.schemas.irregular_item import (
    IrregularFundingCreate,
    IrregularFundPlan,
    IrregularItemCreate,
    IrregularItemResponse,
    IrregularItemUpdate,
)
from kaleta.services import (
    AccountService,
    CategoryService,
    IrregularItemService,
    with_session,
)
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.layout import page_layout
from kaleta.views.theme import BODY_MUTED, PAGE_TITLE, SECTION_CARD, SECTION_HEADING

FUNDS_URL = "/wizard/safety-funds"


def fund_url(fund_id: int) -> str:
    return f"{FUNDS_URL}/{fund_id}"


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _first_of_next_month() -> datetime.date:
    today = datetime.date.today()
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return datetime.date(year, month, 1)


def _month_options() -> dict[int, str]:
    return {m: t(f"payment_calendar.month_{m}") for m in range(1, 13)}


def _parse_amount(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount > 0 else None


def register() -> None:
    @ui.page(f"{FUNDS_URL}/{{fund_id}}")
    async def irregular_fund_page(fund_id: int) -> None:
        async def _reference(session: Any) -> tuple[dict[int, str], dict[int, str]]:
            accounts = {a.id: a.name for a in await AccountService(session).list()}
            categories = await CategoryService(session).list()
            expense = CategoryService.build_option_labels(
                [c for c in categories if c.type == CategoryType.EXPENSE]
            )
            return accounts, expense

        try:
            accounts, categories = await with_session(_reference)

            async def _first_plan(session: Any) -> IrregularFundPlan:
                return await IrregularItemService(session).plan(fund_id)

            first = await with_session(_first_plan)
        except KaletaError:
            # Not an irregular fund (or gone): the funds list is where to be.
            ui.navigate.to(FUNDS_URL)
            return

        with page_layout(first.fund_name, wide=True):
            with ui.column().classes("gap-1"):
                ui.link(t("irregular_fund.back"), FUNDS_URL).classes(f"{BODY_MUTED} text-sm")
                ui.label(first.fund_name).classes(PAGE_TITLE)
                ui.label(t("irregular_fund.subtitle")).classes(BODY_MUTED)
            await _FundPage(fund_id, accounts, categories).render()


class _FundPage:
    """The page's two cards over one refreshable plan."""

    def __init__(self, fund_id: int, accounts: dict[int, str], categories: dict[int, str]) -> None:
        self.fund_id = fund_id
        self.accounts = accounts
        self.categories = categories
        self.editing: IrregularItemResponse | None = None

    async def render(self) -> None:
        self._build_item_dialog()
        await self.body()

    async def _plan(self) -> IrregularFundPlan:
        async def _load(session: Any) -> IrregularFundPlan:
            return await IrregularItemService(session).plan(self.fund_id)

        return await with_session(_load)

    # ── The item dialog ───────────────────────────────────────────────────

    def _build_item_dialog(self) -> None:
        self.dialog = ui.dialog()
        with self.dialog, ui.card().classes("w-[420px] gap-3"):
            self.dialog_title = ui.label("").classes("text-lg font-semibold")
            self.name_in = ui.input(t("irregular_fund.item_name")).classes("w-full")
            self.yearly_in = (
                ui.number(t("irregular_fund.yearly_amount"), min=0, step=10, format="%.2f")
                .classes("w-full")
                .on_value_change(lambda _e: self._preview())
            )
            self.preview = (
                ui.label("")
                .classes(f"{BODY_MUTED} text-sm")
                .props('data-testid="irregular-item-preview"')
            )
            self.month_in = ui.select(
                _month_options(), label=t("irregular_fund.due_month"), clearable=True
            ).classes("w-full")
            self.category_in = ui.select(
                self.categories, label=t("irregular_fund.category"), clearable=True
            ).classes("w-full")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("common.cancel"), on_click=self.dialog.close).props("flat")
                ui.button(t("common.save"), on_click=self._save).props("color=primary")

    def _preview(self) -> None:
        amount = _parse_amount(self.yearly_in.value)
        self.preview.set_text(
            t(
                "irregular_fund.preview",
                monthly=_fmt(IrregularItemService.monthly_contribution(amount)),
            )
            if amount is not None
            else ""
        )

    def _open(self, item: IrregularItemResponse | None) -> None:
        self.editing = item
        self.dialog_title.set_text(
            t("irregular_fund.edit_item") if item else t("irregular_fund.add_item")
        )
        self.name_in.set_value(item.name if item else "")
        self.yearly_in.set_value(float(item.yearly_amount) if item else None)
        self.month_in.set_value(item.due_month if item else None)
        self.category_in.set_value(item.category_id if item else None)
        self._preview()
        self.dialog.open()

    async def _save(self) -> None:
        name = (self.name_in.value or "").strip()
        amount = _parse_amount(self.yearly_in.value)
        if not name or amount is None:
            ui.notify(t("irregular_fund.item_incomplete"), type="negative")
            return
        editing = self.editing

        async def _write(session: Any) -> None:
            svc = IrregularItemService(session)
            if editing is None:
                await svc.create(
                    self.fund_id,
                    IrregularItemCreate(
                        name=name,
                        yearly_amount=amount,
                        due_month=self.month_in.value,
                        category_id=self.category_in.value,
                    ),
                )
            else:
                await svc.update(
                    editing.id,
                    IrregularItemUpdate(
                        name=name,
                        yearly_amount=amount,
                        due_month=self.month_in.value,
                        category_id=self.category_in.value,
                    ),
                )

        try:
            await with_session(_write)
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return
        self.dialog.close()
        ui.notify(t("irregular_fund.item_saved"), type="positive")
        self.body.refresh()

    async def _delete(self, item: IrregularItemResponse) -> None:
        async def _remove(session: Any) -> None:
            await IrregularItemService(session).delete(item.id)

        try:
            await with_session(_remove)
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return
        ui.notify(t("irregular_fund.item_deleted"), type="positive")
        self.body.refresh()

    # ── The page body ─────────────────────────────────────────────────────

    @ui.refreshable_method
    async def body(self) -> None:
        plan = await self._plan()
        self._items_card(plan)
        self._funding_card(plan)

    def _items_card(self, plan: IrregularFundPlan) -> None:
        months = _month_options()
        with ui.card().classes(SECTION_CARD):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("irregular_fund.items_title")).classes(SECTION_HEADING)
                ui.button(
                    t("irregular_fund.add_item"), icon="add", on_click=lambda: self._open(None)
                ).props("flat dense no-caps color=primary")
            if not plan.items:
                ui.label(t("irregular_fund.no_items")).classes(BODY_MUTED)
                return
            with ui.row().classes("w-full px-2 text-xs font-medium border-b " + BODY_MUTED):
                ui.label(t("irregular_fund.item_name")).classes("flex-1")
                ui.label(t("irregular_fund.due_month")).classes("w-32")
                ui.label(t("irregular_fund.yearly_amount")).classes("w-32 text-right")
                ui.label(t("irregular_fund.monthly")).classes("w-32 text-right")
                ui.label("").classes("w-20")
            for item in plan.items:
                with (
                    ui.row()
                    .classes("w-full px-2 py-1 items-center border-b")
                    .props(f'data-testid="irregular-item-{item.id}"')
                ):
                    ui.label(item.name).classes("flex-1")
                    ui.label(months.get(item.due_month, "—") if item.due_month else "—").classes(
                        "w-32 text-sm"
                    )
                    ui.label(_fmt(item.yearly_amount)).classes("w-32 text-right k-mono")
                    ui.label(_fmt(item.monthly_contribution)).classes(
                        "w-32 text-right k-mono font-semibold"
                    ).props('data-testid="irregular-item-monthly"')
                    with ui.row().classes("w-20 justify-end gap-0"):
                        ui.button(icon="edit", on_click=lambda _e, i=item: self._open(i)).props(
                            "flat dense round size=sm color=grey-7"
                        ).tooltip(t("common.edit"))
                        ui.button(icon="delete", on_click=lambda _e, i=item: self._delete(i)).props(
                            "flat dense round size=sm color=negative"
                        ).tooltip(t("common.delete"))
            with ui.row().classes("w-full px-2 pt-2 items-center font-semibold"):
                ui.label(t("common.total")).classes("flex-1")
                ui.label("").classes("w-32")
                ui.label(_fmt(plan.yearly_total)).classes("w-32 text-right k-mono")
                ui.label(_fmt(plan.monthly_total)).classes("w-32 text-right k-mono").props(
                    'data-testid="irregular-monthly-total"'
                )
                ui.label("").classes("w-20")

    def _funding_card(self, plan: IrregularFundPlan) -> None:
        with ui.card().classes(SECTION_CARD):
            ui.label(t("irregular_fund.funding_title")).classes(SECTION_HEADING)
            if plan.backing_account_id is None:
                ui.label(t("irregular_fund.needs_account")).classes(BODY_MUTED)
                return
            if not plan.items:
                ui.label(t("irregular_fund.needs_items")).classes(BODY_MUTED)
                return
            target = self.accounts.get(plan.backing_account_id, "—")
            ui.label(
                t("irregular_fund.funding_body", amount=_fmt(plan.monthly_total), account=target)
            ).classes("text-sm")
            sources = {k: v for k, v in self.accounts.items() if k != plan.backing_account_id}
            if not sources:
                ui.label(t("irregular_fund.needs_source")).classes(BODY_MUTED)
                return
            with ui.row().classes("w-full items-end gap-3"):
                source = ui.select(
                    sources, label=t("irregular_fund.from_account"), value=next(iter(sources))
                ).classes("w-64")
                start = ui.input(
                    t("irregular_fund.start_date"), value=str(_first_of_next_month())
                ).props("type=date")

                async def _create() -> None:
                    try:
                        start_date = datetime.date.fromisoformat(start.value)
                    except (TypeError, ValueError):
                        start_date = _first_of_next_month()
                    payload = IrregularFundingCreate(
                        from_account_id=source.value, start_date=start_date
                    )

                    async def _write(session: Any) -> None:
                        await IrregularItemService(session).create_funding_plan(
                            self.fund_id, payload
                        )

                    try:
                        await with_session(_write)
                    except KaletaError as exc:
                        notify_kaleta_error(exc)
                        return
                    ui.notify(
                        t("irregular_fund.funding_created", amount=_fmt(plan.monthly_total)),
                        type="positive",
                    )

                ui.button(t("irregular_fund.create_funding"), on_click=_create).props(
                    "color=primary no-caps"
                )
