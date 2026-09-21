# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.schemas.account import AccountType
from kaleta.schemas.asset import AssetCreate, AssetType, AssetUpdate
from kaleta.services import AssetService, NetWorthService, with_session
from kaleta.services.net_worth_service import (
    AccountSnapshot,
    NetWorthSummary,
    PhysicalAssetSnapshot,
    balance_sheet_split,
)
from kaleta.views.chart_utils import (
    AXIS_LABEL_BODY,
    AXIS_LABEL_MONO,
    AXIS_VALUE_SPACED,
    apply_dark,
    chart_expense_color,
    chart_income_color,
)
from kaleta.views.components.amount_label import (
    format_net_amount,
    net_tone,
    spaced_thousands,
)
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    ASSET_ADD,
    ASSET_ROW,
    CARD_NOTE,
    CARD_TITLE,
    CARD_TITLE_SM,
    DELTA_FIGURE,
    DELTA_LABEL,
    INK,
    INK_2,
    LEGEND_DOT,
    MONO,
    MUTED,
    NET_WORTH_DECIMALS,
    NET_WORTH_FIGURE,
    PAGE_CONTAINER,
    PAGE_EYEBROW,
    PAGE_ROOMY,
    SECTION_CARD,
    SECTION_CARD_FEATURE,
    SECTION_CARD_WIDE,
    SHEET_HEAD,
    SHEET_ROW,
    SPLIT_BAR,
)


def _type_label() -> dict[AccountType, str]:
    return {
        AccountType.CHECKING: t("accounts.checking"),
        AccountType.SAVINGS: t("accounts.savings"),
        AccountType.CASH: t("accounts.cash"),
        AccountType.CREDIT: t("accounts.credit"),
    }


def _asset_type_label() -> dict[str, str]:
    return {
        AssetType.REAL_ESTATE.value: t("net_worth.real_estate"),
        AssetType.VEHICLE.value: t("net_worth.vehicle"),
        AssetType.VALUABLES.value: t("net_worth.valuables"),
        AssetType.OTHER.value: t("net_worth.other"),
    }


def _fmt(amount: Decimal, currency: str = "PLN") -> str:
    return spaced_thousands(f"{amount:,.2f} {currency}")


def sheet_balance(balance: Decimal, *, is_asset: bool) -> Decimal:
    """The figure a balance-sheet row shows for an account.

    An owed balance is drawn negative and in the expense colour, which is
    what artboard `3b` writes: the card's total is the unsigned size of the
    debt and the rows under it say which way it points. `-abs` rather than a
    negation, because a liability account already holds a negative balance
    and negating that one drew the debt as a credit — which is what this
    screen was doing. An overpaid card, whose balance really is positive,
    is still money the account owes back and reads the same way.
    """
    return balance if is_asset else -abs(balance)


def split_figure(amount: Decimal, currency: str = "PLN") -> tuple[str, str]:
    """The headline figure as (whole, remainder) — ``1,234,567`` and ``.89 PLN``.

    At 54px the grosze are the least interesting thing on the page and the
    loudest; splitting them off lets the decimals be muted without the two
    halves ever disagreeing about rounding.
    """
    whole, _, cents = spaced_thousands(f"{amount:,.2f}").partition(".")
    return whole, f".{cents} {currency}"


def _delta(label: str, delta: Decimal | None, currency: str) -> None:
    """A 'label ±value' chip, in the same tones the ledger uses for direction."""
    tone = MUTED if delta is None else net_tone(delta)
    # No pill: artboard `3b` sets the two deltas as bare type under the
    # figure, because a pill around a number reads as something to press.
    with ui.row().classes("items-baseline gap-2"):
        ui.label(label).classes(DELTA_LABEL)
        if delta is None:
            ui.label("—").classes(f"{DELTA_FIGURE} {MUTED}")
            return
        ui.label(spaced_thousands(format_net_amount(delta))).classes(f"{DELTA_FIGURE} {tone}")


def _header_strip(summary: NetWorthSummary, currency: str) -> None:
    """The headline, left-aligned, with its two deltas beside it.

    Centred, the figure had nothing to line up with; against the left margin
    it shares an edge with everything below it.
    """
    tone = INK if summary.net_worth >= 0 else AMOUNT_EXPENSE
    whole, remainder = split_figure(summary.net_worth, currency)
    with ui.column().classes("w-full gap-0"):
        ui.label(t("net_worth.eyebrow", months=len(summary.history) or 13)).classes(
            PAGE_EYEBROW
        ).props("data-page-eyebrow")
        with ui.row().classes("items-baseline gap-3 flex-wrap mt-1.5"):
            ui.label(whole).classes(f"{NET_WORTH_FIGURE} {tone}")
            ui.label(remainder).classes(NET_WORTH_DECIMALS)
        with ui.row().classes("gap-7 flex-wrap mt-4"):
            _delta(t("net_worth.vs_30d_ago"), summary.delta_30d, currency)
            _delta(t("net_worth.vs_start_of_year"), summary.delta_ytd, currency)


def _balance_sheet_bar(summary: NetWorthSummary, currency: str) -> None:
    """One bar, three segments: what is held, what is owned, what is owed.

    The shape of the sheet before any table — the same net worth can be
    10 000 owned outright or 200 000 owned against 190 000 owed, and those
    are not the same position.
    """
    split = balance_sheet_split(summary)
    if split is None:
        return

    segments = (
        (t("net_worth.split_accounts"), split.accounts, summary.account_assets, "k-split--asset"),
        (
            t("net_worth.split_physical"),
            split.physical,
            summary.total_physical_assets,
            "k-split--asset-soft",
        ),
        (
            t("net_worth.split_liabilities"),
            split.liabilities,
            summary.total_liabilities,
            "k-split--owed",
        ),
    )

    with ui.column().classes("w-full gap-0 max-w-[620px] mt-[26px]"):
        # A plain div, not ui.row: nicegui-row puts a default gap between
        # its children, and a gap here would be read as a fourth segment.
        with ui.element("div").classes(f"{SPLIT_BAR} w-full"):
            for label, pct, amount, tone in segments:
                if pct <= 0:
                    continue
                seg = ui.element("div").classes(f"k-split-seg {tone}").style(f"width:{pct:.4f}%")
                seg.props["aria-label"] = f"{label}: {_fmt(amount, currency)}"
        # The share is the bar; printing it again beside the figure says the
        # same thing twice and costs the legend the room to say the figure.
        with ui.row().classes("gap-[26px] flex-wrap mt-[11px]"):
            for label, _pct, amount, tone in segments:
                with ui.row().classes("items-center gap-[7px]"):
                    ui.element("div").classes(f"k-split-dot {tone}")
                    ui.label(label).classes(f"{INK_2} text-xs")
                    ui.label(_fmt(amount, currency)).classes(f"{MONO} {INK} text-xs")


def _chart(summary: NetWorthSummary, dark: bool) -> None:
    """Stacked area of assets vs liabilities over time.

    Liabilities are plotted as positive values stacked on top of assets so the
    top of the combined area reads as (assets + liabilities) — while the
    net-worth value in the header remains the difference. The intent is to
    convey the *size* of both sides at a glance.
    """
    ui.echart(net_worth_chart_options(summary, dark)).classes("w-full h-[260px]")


#: How solid the two area fills are. They used to be solid enough that the
#: upper band was the loudest thing on the page and the lower one was hard to
#: read underneath it.
_FILL_OPACITY = 0.22


def net_worth_chart_options(summary: NetWorthSummary, dark: bool) -> dict[str, Any]:
    """The stacked chart's options, separated so the stacking can be tested."""
    labels = [s.label for s in summary.history]
    assets_k = [round(float(s.total_assets) / 1000, 1) for s in summary.history]
    liabilities_k = [round(float(s.total_liabilities) / 1000, 1) for s in summary.history]
    assets_color = chart_income_color(dark)
    liabilities_color = chart_expense_color(dark)

    def _series(name: str, data: list[float], color: str) -> dict[str, Any]:
        return {
            "name": name,
            "type": "line",
            "stack": "total",
            "data": data,
            "smooth": True,
            "symbol": "circle",
            "symbolSize": 4,
            "lineStyle": {"color": color, "width": 2},
            "itemStyle": {"color": color},
            "areaStyle": {"color": color, "opacity": _FILL_OPACITY},
            # Each line says what it ends at, so the reader does not have to
            # hover to find out where the chart leaves them.
            "endLabel": {
                "show": True,
                "formatter": "{c}k",
                "color": color,
                "fontSize": 11,
            },
        }

    options: dict[str, Any] = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        # No legend inside the plot: artboard `3b` puts the key on the card's
        # title line, where the reader is already looking, and what the upper
        # band means is said in the subtitle beside it.
        "grid": {"left": 56, "right": 92, "top": 12, "bottom": 34},
        "xAxis": {
            "type": "category",
            "data": labels,
            # Horizontal, and ECharts drops whatever will not fit: thirteen
            # months at 45 degrees cost the chart a third of its height to
            # say what seven of them already say.
            "axisLabel": AXIS_LABEL_BODY,
            "axisTick": {"show": False},
            "axisLine": {"show": False},
        },
        "yAxis": {
            "type": "value",
            # From zero: a floating baseline makes a steady balance sheet look
            # like a cliff.
            "min": 0,
            # No axis name: the labels already end in `k`, and "tys. PLN"
            # turned sideways is the only rotated type on the page.
            # The grouping the rest of the screen writes: ECharts' own
            # `{value}` puts a comma in at four figures, and `1,200k` beside
            # `901 393.51 PLN` is one screen writing a thousand two ways.
            # `:`-prefixed, so NiceGUI hands the string over as a function.
            "axisLabel": {
                **AXIS_LABEL_MONO,
                ":formatter": f"{AXIS_VALUE_SPACED} + 'k'",
            },
            "axisLine": {"show": False},
            "axisTick": {"show": False},
        },
        "series": [
            _series(t("net_worth.assets"), assets_k, assets_color),
            _series(t("net_worth.chart_liabilities_stacked"), liabilities_k, liabilities_color),
        ],
    }
    return apply_dark(options, dark)


def _account_table(
    accounts: list[AccountSnapshot], assets: bool, default_currency: str = "PLN"
) -> None:
    filtered = [a for a in accounts if a.is_asset == assets]
    filtered.sort(key=lambda a: abs(a.balance_in_default), reverse=True)
    if not filtered:
        ui.label(t("common.none")).classes(f"{MUTED} text-sm py-2")
        return

    type_labels = _type_label()
    with ui.element("div").classes(f"{SHEET_HEAD} w-full mt-3.5"):
        ui.label(t("common.account"))
        ui.label(t("common.type"))
        ui.label(t("common.institution"))
        ui.label(t("common.balance")).classes("text-right")
    for a in filtered:
        balance = (
            f"{_fmt(a.balance, a.currency)} ≈ {_fmt(a.balance_in_default, default_currency)}"
            if a.currency != default_currency
            else _fmt(sheet_balance(a.balance, is_asset=assets), a.currency)
        )
        with ui.element("div").classes(f"{SHEET_ROW} w-full"):
            ui.label(a.name)
            ui.label(type_labels.get(a.type, a.type.value)).classes(f"{MUTED} text-[11.5px]")
            ui.label(a.institution_name or "—").classes(MUTED)
            ui.label(balance).classes(f"{MONO} text-right {'' if assets else AMOUNT_EXPENSE}")


def _loans_footnote() -> None:
    """What the two tables above deliberately leave out.

    Money lent to a friend is an asset by any honest reckoning, but the app
    tracks it on its own page and not in the balance sheet — so the tables
    say where it lives instead of quietly under-counting.
    """
    with ui.row().classes(f"{CARD_NOTE} w-full mt-4"):
        ui.icon("handshake", size="16px").classes(MUTED)
        with ui.row().classes("items-baseline gap-1.5 flex-wrap"):
            ui.label(t("net_worth.loans_footnote"))
            ui.link(t("net_worth.loans_footnote_link"), "/wizard/personal-loans").classes(
                "text-xs underline"
            )


def _physical_assets_section(summary: NetWorthSummary) -> None:
    """Renders the physical assets card with CRUD controls. All dialogs pre-created at render."""

    type_options = _asset_type_label()
    editing: dict[str, Any] = {"id": None, "snapshot": None}

    @ui.refreshable
    def assets_ui() -> None:
        if not summary.physical_assets:
            ui.label(t("net_worth.no_assets")).classes(f"{MUTED} text-sm py-2")
            return

        asset_type_labels = _asset_type_label()
        # Four columns and no header: artboard `3b` reads this card as a list
        # of things you own, not as a table you sort. The note each asset can
        # carry is on the row's tooltip — it was a fifth column, and a fifth
        # column is what pushed the value off a 420px card.
        for a in summary.physical_assets:
            row = ui.element("div").classes(f"{ASSET_ROW} w-full")
            with row:
                ui.label(a.name).classes("truncate")
                ui.label(asset_type_labels.get(a.type, a.type)).classes(f"{MUTED} text-[11.5px]")
                # No currency on the row: the card's title line carries it
                # once, and repeating it three times costs the value column
                # the width it needs to stay on one line.
                ui.label(spaced_thousands(f"{a.value:,.2f}")).classes(f"{MONO} text-right")
                with ui.row().classes("justify-end gap-0"):
                    ui.button(
                        icon="edit", on_click=lambda _e, i=a.id: _on_edit({"id": i}), color=None
                    ).props("flat dense round size=sm").classes(MUTED)
                    ui.button(
                        icon="delete",
                        on_click=lambda _e, i=a.id: _on_delete({"id": i}),
                        color=None,
                    ).props("flat dense round size=sm").classes(MUTED)
            if a.description:
                row.tooltip(a.description)

    assets_ui()

    # ── Add dialog ────────────────────────────────────────────────────────────
    add_dlg = ui.dialog()
    with add_dlg, ui.card().classes("w-96"):
        ui.label(t("net_worth.add_asset_title")).classes("text-lg font-semibold mb-2")
        add_name = ui.input(t("net_worth.asset_name")).classes("w-full")
        add_type = ui.select(
            type_options, label=t("net_worth.asset_type"), value=AssetType.OTHER.value
        ).classes("w-full")
        add_value = ui.number(t("net_worth.asset_value"), value=0, min=0, step=1000).classes(
            "w-full"
        )
        add_desc = ui.input(t("net_worth.asset_note")).classes("w-full")

        async def _add_save() -> None:
            async def _create(session: Any) -> Any:
                return await AssetService(session).create(
                    AssetCreate(
                        name=add_name.value or "",
                        type=AssetType(add_type.value),
                        value=Decimal(str(add_value.value or 0)),
                        description=add_desc.value or "",
                    )
                )

            asset = await with_session(_create)
            summary.physical_assets.append(
                PhysicalAssetSnapshot(
                    id=asset.id,
                    name=asset.name,
                    type=asset.type.value,
                    value=asset.value,
                    description=asset.description,
                )
            )
            assets_ui.refresh()
            add_dlg.close()

        def _add_reset() -> None:
            add_name.set_value("")
            add_type.set_value(AssetType.OTHER.value)
            add_value.set_value(0)
            add_desc.set_value("")

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=add_dlg.close).props("flat")
            ui.button(t("common.save"), on_click=_add_save).props("color=primary")

    # ── Edit dialog ───────────────────────────────────────────────────────────
    edit_dlg = ui.dialog()
    with edit_dlg, ui.card().classes("w-96"):
        ui.label(t("net_worth.edit_asset")).classes("text-lg font-semibold mb-2")
        edit_name = ui.input(t("net_worth.asset_name")).classes("w-full")
        edit_type = ui.select(
            type_options, label=t("net_worth.asset_type"), value=AssetType.OTHER.value
        ).classes("w-full")
        edit_value = ui.number(t("net_worth.asset_value"), value=0, min=0, step=1000).classes(
            "w-full"
        )
        edit_desc = ui.input(t("net_worth.asset_note")).classes("w-full")

        async def _edit_save() -> None:
            snap: PhysicalAssetSnapshot = editing["snapshot"]

            async def _update(session: Any) -> Any:
                return await AssetService(session).update(
                    editing["id"],
                    AssetUpdate(
                        name=edit_name.value or snap.name,
                        type=AssetType(edit_type.value),
                        value=Decimal(str(edit_value.value or 0)),
                        description=edit_desc.value,
                    ),
                )

            updated = await with_session(_update)
            if updated:
                snap.name = updated.name
                snap.type = updated.type.value
                snap.value = updated.value
                snap.description = updated.description
            assets_ui.refresh()
            edit_dlg.close()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=edit_dlg.close).props("flat")
            ui.button(t("common.save"), on_click=_edit_save).props("color=primary")

    # ── Delete dialog ─────────────────────────────────────────────────────────
    del_dlg = ui.dialog()
    with del_dlg, ui.card().classes("w-80"):
        del_label = ui.label("").classes("text-lg font-semibold")
        ui.label(t("net_worth.cannot_undo")).classes("text-sm text-slate-500 mt-1")

        async def _del_confirm() -> None:
            async def _delete(session: Any) -> None:
                await AssetService(session).delete(editing["id"])

            await with_session(_delete)
            summary.physical_assets[:] = [
                a for a in summary.physical_assets if a.id != editing["id"]
            ]
            assets_ui.refresh()
            del_dlg.close()

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button(t("common.cancel"), on_click=del_dlg.close).props("flat")
            ui.button(t("common.delete"), on_click=_del_confirm).props("color=negative")

    # ── Event handlers ────────────────────────────────────────────────────────
    def _on_edit(row: dict[str, Any]) -> None:
        snap = next((a for a in summary.physical_assets if a.id == row["id"]), None)
        if snap is None:
            return
        editing["id"] = snap.id
        editing["snapshot"] = snap
        edit_name.set_value(snap.name)
        edit_type.set_value(snap.type)
        edit_value.set_value(float(snap.value))
        edit_desc.set_value(snap.description)
        edit_dlg.open()

    def _on_delete(row: dict[str, Any]) -> None:
        snap = next((a for a in summary.physical_assets if a.id == row["id"]), None)
        if snap is None:
            return
        editing["id"] = snap.id
        del_label.set_text(t("net_worth.delete_asset_confirm", name=snap.name))
        del_dlg.open()

    def _on_add() -> None:
        _add_reset()
        add_dlg.open()

    # Under a rule of its own, as artboard `3b` draws it: the line that adds
    # one is not another asset in the list. The rule spans the card, so it is
    # on a row of its own rather than on the button.
    with ui.row().classes(f"{ASSET_ADD} w-full"):
        ui.button(t("net_worth.add_asset"), icon="add", on_click=_on_add, color=None).props(
            "flat dense no-caps size=sm"
        ).classes("k-asset-add-btn")


def register() -> None:
    @ui.page("/net-worth")
    async def net_worth_page() -> None:
        dark: bool = app.storage.user.get("dark_mode", False)
        default_currency: str = app.storage.user.get("currency", "PLN")

        async def _load_summary(session: Any) -> NetWorthSummary:
            return await NetWorthService(session).get_summary(
                history_months=13,
                default_currency=default_currency,
            )

        summary = await with_session(_load_summary)

        with page_layout(
            t("net_worth.title"),
            wide=True,
            container=f"{PAGE_CONTAINER} {PAGE_ROOMY}",
        ):
            # The hero sits on the ground, not on paper: it is the page's
            # subject, and a card round it would make it one of four.
            with ui.row().classes("w-full gap-12 items-start no-wrap flex-wrap lg:flex-nowrap"):
                with ui.column().classes("flex-1 min-w-0 gap-0"):
                    _header_strip(summary, default_currency)
                    _balance_sheet_bar(summary, default_currency)

                with ui.card().classes(
                    f"{SECTION_CARD_WIDE} w-full lg:w-[420px] lg:flex-none min-w-0 gap-0"
                ):
                    with ui.row().classes("w-full items-center justify-between mb-3.5"):
                        ui.label(t("net_worth.physical_assets")).classes(CARD_TITLE_SM)
                        ui.label(_fmt(summary.total_physical_assets, default_currency)).classes(
                            f"{MONO} {INK} text-[13px] font-medium"
                        )
                    _physical_assets_section(summary)

            # ── Stacked trend chart ───────────────────────────────────────────
            with ui.card().classes(f"{SECTION_CARD_FEATURE} gap-0"):
                with ui.row().classes("w-full items-baseline justify-between mb-4"):
                    with ui.column().classes("gap-1 min-w-0"):
                        ui.label(t("net_worth.history")).classes(CARD_TITLE)
                        ui.label(t("net_worth.history_hint")).classes(f"{MUTED} text-[11.5px]")
                    # The key belongs on the title line, where the reader is
                    # already looking, and not inside the plot.
                    with ui.row().classes(f"{MUTED} gap-4 text-[11.5px] no-wrap"):
                        for label_key, tone in (
                            ("net_worth.assets", "k-split--asset"),
                            ("net_worth.liabilities", "k-split--owed"),
                        ):
                            with ui.row().classes("items-center gap-1.5"):
                                ui.element("div").classes(f"{LEGEND_DOT} {tone}")
                                ui.label(t(label_key))
                _chart(summary, dark)

            # ── Assets / Liabilities two-column split ─────────────────────────
            with ui.row().classes("w-full gap-5 items-start flex-wrap lg:flex-nowrap"):
                with ui.card().classes(f"{SECTION_CARD} flex-1 min-w-80 gap-0"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(t("net_worth.assets")).classes(CARD_TITLE_SM)
                        ui.label(_fmt(summary.total_assets, default_currency)).classes(
                            f"{MONO} {AMOUNT_INCOME} text-sm font-medium"
                        )
                    _account_table(summary.accounts, assets=True, default_currency=default_currency)

                with ui.card().classes(f"{SECTION_CARD} flex-1 min-w-80 gap-0"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(t("net_worth.liabilities")).classes(CARD_TITLE_SM)
                        ui.label(_fmt(summary.total_liabilities, default_currency)).classes(
                            f"{MONO} {AMOUNT_EXPENSE} text-sm font-medium"
                        )
                    _account_table(
                        summary.accounts, assets=False, default_currency=default_currency
                    )
                    # The note belongs to the side it is about: what is missing
                    # from the liabilities is money the app keeps elsewhere.
                    _loans_footnote()
