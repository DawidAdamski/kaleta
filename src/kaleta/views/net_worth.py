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
    apply_dark,
    chart_expense_color,
    chart_income_color,
)
from kaleta.views.components.amount_label import format_net_amount, net_tone
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    FILTER_CHIP,
    INK,
    MONO,
    MUTED,
    SECTION_CARD,
    SECTION_HEADING,
    SECTION_TITLE,
    SPLIT_BAR,
    TABLE_SURFACE,
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
    return f"{amount:,.2f} {currency}"


def split_figure(amount: Decimal, currency: str = "PLN") -> tuple[str, str]:
    """The headline figure as (whole, remainder) — ``1,234,567`` and ``.89 PLN``.

    At 54px the grosze are the least interesting thing on the page and the
    loudest; splitting them off lets the decimals be muted without the two
    halves ever disagreeing about rounding.
    """
    whole, _, cents = f"{amount:,.2f}".partition(".")
    return whole, f".{cents} {currency}"


def _delta_pill(label: str, delta: Decimal | None, currency: str) -> None:
    """A 'label ±value' chip, in the same tones the ledger uses for direction."""
    tone = MUTED if delta is None else net_tone(delta)
    with ui.row().classes(f"{FILTER_CHIP} items-center gap-1.5"):
        ui.label(label).classes(f"{MUTED} text-[11px]")
        if delta is None:
            ui.label("—").classes(f"{MONO} text-xs {MUTED}")
            return
        ui.icon("arrow_upward" if delta >= 0 else "arrow_downward", size="13px").classes(tone)
        ui.label(f"{format_net_amount(delta)} {currency}").classes(f"{MONO} text-xs {tone}")


def _header_strip(summary: NetWorthSummary, currency: str) -> None:
    """The headline, left-aligned, with its two deltas beside it.

    Centred, the figure had nothing to line up with; against the left margin
    it shares an edge with everything below it.
    """
    tone = INK if summary.net_worth >= 0 else AMOUNT_EXPENSE
    whole, remainder = split_figure(summary.net_worth, currency)
    with ui.column().classes("w-full gap-1"):
        ui.label(t("net_worth.net_worth")).classes(SECTION_TITLE)
        with ui.row().classes("items-baseline gap-2 flex-wrap"):
            ui.label(whole).classes(f"{MONO} {tone} text-[54px] leading-none font-light")
            ui.label(remainder).classes(f"{MONO} {MUTED} text-lg")
            with ui.row().classes("items-center gap-2 ml-2 flex-wrap"):
                _delta_pill(t("net_worth.vs_30d_ago"), summary.delta_30d, currency)
                _delta_pill(t("net_worth.vs_start_of_year"), summary.delta_ytd, currency)


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
        (t("net_worth.split_accounts"), split.accounts, summary.account_assets, "k-split--ink"),
        (
            t("net_worth.split_physical"),
            split.physical,
            summary.total_physical_assets,
            "k-split--neutral",
        ),
        (
            t("net_worth.split_liabilities"),
            split.liabilities,
            summary.total_liabilities,
            "k-split--owed",
        ),
    )

    with ui.column().classes("w-full gap-2"):
        # A plain div, not ui.row: nicegui-row puts a default gap between
        # its children, and a gap here would be read as a fourth segment.
        with ui.element("div").classes(f"{SPLIT_BAR} w-full"):
            for label, pct, amount, tone in segments:
                if pct <= 0:
                    continue
                seg = ui.element("div").classes(f"k-split-seg {tone}").style(f"width:{pct:.4f}%")
                seg.props["aria-label"] = f"{label}: {_fmt(amount, currency)}"
        with ui.row().classes("gap-5 flex-wrap"):
            for label, pct, amount, tone in segments:
                with ui.row().classes("items-center gap-1.5"):
                    ui.element("div").classes(f"k-split-dot {tone}")
                    ui.label(label).classes(f"{MUTED} text-xs")
                    ui.label(_fmt(amount, currency)).classes(f"{MONO} text-xs")
                    ui.label(f"{pct:.0f}%").classes(f"{MUTED} {MONO} text-xs")


def _chart(summary: NetWorthSummary, dark: bool) -> None:
    """Stacked area of assets vs liabilities over time.

    Liabilities are plotted as positive values stacked on top of assets so the
    top of the combined area reads as (assets + liabilities) — while the
    net-worth value in the header remains the difference. The intent is to
    convey the *size* of both sides at a glance.
    """
    ui.echart(net_worth_chart_options(summary, dark)).classes("w-full h-64")


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
        "legend": {
            # The upper edge is assets *plus* liabilities, not net worth. The
            # legend says so rather than leaving the reader to infer it from a
            # line that looks like a total.
            "data": [t("net_worth.assets"), t("net_worth.chart_liabilities_stacked")],
            "top": 0,
        },
        "grid": {"left": "10%", "right": "10%", "top": "12%", "bottom": "18%"},
        "xAxis": {
            "type": "category",
            "data": labels,
            "axisLabel": {"rotate": 45, "fontSize": 11},
        },
        "yAxis": {
            "type": "value",
            # From zero: a floating baseline makes a steady balance sheet look
            # like a cliff.
            "min": 0,
            "name": t("net_worth.thousand_pln"),
            "nameTextStyle": {"fontSize": 10},
            "axisLabel": {"formatter": "{value}k"},
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

    columns = [
        {"name": "name", "label": t("common.account"), "field": "name", "align": "left"},
        {"name": "type", "label": t("common.type"), "field": "type", "align": "left"},
        {
            "name": "institution",
            "label": t("common.institution"),
            "field": "institution",
            "align": "left",
        },
        {"name": "balance", "label": t("common.balance"), "field": "balance", "align": "right"},
    ]
    type_labels = _type_label()
    rows = [
        {
            "name": a.name,
            "type": type_labels.get(a.type, a.type.value),
            "institution": a.institution_name or "—",
            "balance": (
                f"{_fmt(a.balance, a.currency)} ≈ {_fmt(a.balance_in_default, default_currency)}"
                if a.currency != default_currency
                else _fmt(a.balance if assets else -a.balance, a.currency)
            ),
        }
        for a in filtered
    ]
    ui.table(columns=columns, rows=rows, row_key="name").classes(f"{TABLE_SURFACE} mt-2").props(
        "flat wrap-cells"
    )


def _loans_footnote() -> None:
    """What the two tables above deliberately leave out.

    Money lent to a friend is an asset by any honest reckoning, but the app
    tracks it on its own page and not in the balance sheet — so the tables
    say where it lives instead of quietly under-counting.
    """
    with ui.row().classes("w-full items-center gap-1.5 flex-wrap"):
        ui.label(t("net_worth.loans_footnote")).classes(f"{MUTED} text-xs")
        ui.link(t("net_worth.loans_footnote_link"), "/wizard/personal-loans").classes(
            f"{MUTED} text-xs underline"
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
        columns = [
            {"name": "name", "label": t("net_worth.asset_name"), "field": "name", "align": "left"},
            {"name": "type", "label": t("net_worth.asset_type"), "field": "type", "align": "left"},
            {
                "name": "value",
                "label": t("net_worth.asset_value"),
                "field": "value",
                "align": "right",
            },
            {"name": "note", "label": t("net_worth.asset_note"), "field": "note", "align": "left"},
            {"name": "actions", "label": "", "field": "actions", "align": "right"},
        ]
        rows = [
            {
                "id": a.id,
                "name": a.name,
                "type": asset_type_labels.get(a.type, a.type),
                "value": _fmt(a.value),
                "note": a.description,
            }
            for a in summary.physical_assets
        ]

        table = (
            ui.table(columns=columns, rows=rows, row_key="id")
            .classes(f"{TABLE_SURFACE} mt-2")
            .props("flat dense")
        )
        table.add_slot(
            "body-cell-actions",
            """
            <q-td :props="props" class="text-right">
                <q-btn flat dense round icon="edit" color="primary"
                    @click="$parent.$emit('edit', props.row)" />
                <q-btn flat dense round icon="delete" color="negative"
                    @click="$parent.$emit('delete', props.row)" />
            </q-td>
            """,
        )
        table.on("edit", lambda e: _on_edit(e.args))
        table.on("delete", lambda e: _on_delete(e.args))

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

    ui.button(t("net_worth.add_asset"), icon="add", on_click=_on_add).props(
        "flat dense color=primary size=sm"
    ).classes("self-start mt-1")


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

        with page_layout(t("net_worth.title")):
            # ── Hero + physical assets side by side from lg up ────────────────
            with ui.row().classes("w-full gap-4 items-start flex-wrap lg:flex-nowrap"):
                with ui.card().classes(
                    f"{SECTION_CARD} basis-full lg:basis-3/5 flex-1 min-w-0 gap-5"
                ):
                    _header_strip(summary, default_currency)
                    _balance_sheet_bar(summary, default_currency)

                with ui.card().classes(
                    f"{SECTION_CARD} basis-full lg:basis-2/5 flex-1 min-w-0 gap-1"
                ):
                    with ui.row().classes("w-full items-baseline justify-between"):
                        ui.label(t("net_worth.physical_assets")).classes(SECTION_HEADING)
                        ui.label(_fmt(summary.total_physical_assets, default_currency)).classes(
                            f"{MONO} {INK} text-sm"
                        )
                    _physical_assets_section(summary)

            # ── Stacked trend chart ───────────────────────────────────────────
            with ui.card().classes(SECTION_CARD):
                ui.label(t("net_worth.history")).classes(SECTION_HEADING)
                _chart(summary, dark)

            # ── Assets / Liabilities two-column split ─────────────────────────
            with ui.row().classes("w-full gap-4 items-start flex-wrap lg:flex-nowrap"):
                with ui.card().classes(f"{SECTION_CARD} flex-1 min-w-80 gap-1"):
                    with ui.row().classes("w-full items-baseline justify-between"):
                        ui.label(t("net_worth.assets")).classes(SECTION_HEADING)
                        ui.label(_fmt(summary.total_assets, default_currency)).classes(
                            f"{MONO} {INK} text-sm"
                        )
                    _account_table(summary.accounts, assets=True, default_currency=default_currency)

                with ui.card().classes(f"{SECTION_CARD} flex-1 min-w-80 gap-1"):
                    with ui.row().classes("w-full items-baseline justify-between"):
                        ui.label(t("net_worth.liabilities")).classes(SECTION_HEADING)
                        ui.label(_fmt(summary.total_liabilities, default_currency)).classes(
                            f"{MONO} {AMOUNT_EXPENSE} text-sm"
                        )
                    _account_table(
                        summary.accounts, assets=False, default_currency=default_currency
                    )

            _loans_footnote()
