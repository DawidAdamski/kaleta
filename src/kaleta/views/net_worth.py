from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.account import AccountType
from kaleta.models.asset import AssetType
from kaleta.schemas.asset import AssetCreate, AssetUpdate
from kaleta.services.asset_service import AssetService
from kaleta.services.net_worth_service import (
    AccountSnapshot,
    NetWorthService,
    NetWorthSummary,
    PhysicalAssetSnapshot,
)
from kaleta.views.layout import page_layout


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


def _delta_pill(label: str, delta: Decimal | None, currency: str) -> None:
    """Renders a 'label: ±value' pill with an arrow indicating direction."""
    with ui.row().classes("items-center gap-1"):
        ui.label(label).classes("text-xs text-grey-6 uppercase tracking-wide")
        if delta is None:
            ui.label("—").classes("text-sm text-grey-5")
            return
        icon = "arrow_upward" if delta >= 0 else "arrow_downward"
        color = "positive" if delta >= 0 else "negative"
        sign = "+" if delta >= 0 else ""
        ui.icon(icon).classes(f"text-{color} text-sm")
        ui.label(f"{sign}{_fmt(delta, currency)}").classes(f"text-sm font-medium text-{color}")


def _header_strip(summary: NetWorthSummary, currency: str) -> None:
    """Top-of-page net-worth headline with 30d + YTD delta pills."""
    color = "primary" if summary.net_worth >= 0 else "negative"
    with (
        ui.card().classes("w-full p-6"),
        ui.column().classes("w-full items-center gap-2"),
    ):
        ui.label(t("net_worth.net_worth")).classes(
            "text-sm text-grey-6 uppercase tracking-wide"
        )
        ui.label(_fmt(summary.net_worth, currency)).classes(f"text-4xl font-bold text-{color}")
        with ui.row().classes("gap-6 mt-1 flex-wrap justify-center"):
            _delta_pill(t("net_worth.vs_30d_ago"), summary.delta_30d, currency)
            _delta_pill(t("net_worth.vs_start_of_year"), summary.delta_ytd, currency)


def _chart(summary: NetWorthSummary, dark: bool) -> None:
    """Stacked area of assets vs liabilities over time.

    Liabilities are plotted as positive values stacked on top of assets so the
    top of the combined area reads as (assets + liabilities) — while the
    net-worth value in the header remains the difference. The intent is to
    convey the *size* of both sides at a glance.
    """
    labels = [s.label for s in summary.history]
    assets_k = [round(float(s.total_assets) / 1000, 1) for s in summary.history]
    liabilities_k = [round(float(s.total_liabilities) / 1000, 1) for s in summary.history]
    text_color = "#e0e0e0" if dark else "#555555"

    ui.echart(
        {
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {
                "data": [t("net_worth.assets"), t("net_worth.liabilities")],
                "textStyle": {"color": text_color},
                "top": 0,
            },
            "grid": {"left": "10%", "right": "4%", "top": "12%", "bottom": "18%"},
            "xAxis": {
                "type": "category",
                "data": labels,
                "axisLabel": {"rotate": 45, "fontSize": 11, "color": text_color},
                "axisLine": {"lineStyle": {"color": text_color}},
            },
            "yAxis": {
                "type": "value",
                "name": t("net_worth.thousand_pln"),
                "nameTextStyle": {"color": text_color, "fontSize": 10},
                "axisLabel": {"formatter": "{value}k", "color": text_color},
                "splitLine": {"lineStyle": {"color": "#444444" if dark else "#e0e0e0"}},
            },
            "series": [
                {
                    "name": t("net_worth.assets"),
                    "type": "line",
                    "stack": "total",
                    "data": assets_k,
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 4,
                    "lineStyle": {"color": "#2e7d32", "width": 2},
                    "itemStyle": {"color": "#2e7d32"},
                    "areaStyle": {"color": "#4caf50", "opacity": 0.35},
                },
                {
                    "name": t("net_worth.liabilities"),
                    "type": "line",
                    "stack": "total",
                    "data": liabilities_k,
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 4,
                    "lineStyle": {"color": "#c62828", "width": 2},
                    "itemStyle": {"color": "#c62828"},
                    "areaStyle": {"color": "#ef5350", "opacity": 0.35},
                },
            ],
        }
    ).classes("w-full h-64")


def _account_table(
    accounts: list[AccountSnapshot], assets: bool, default_currency: str = "PLN"
) -> None:
    filtered = [a for a in accounts if a.is_asset == assets]
    filtered.sort(key=lambda a: abs(a.balance_in_default), reverse=True)
    if not filtered:
        ui.label(t("common.none")).classes("text-grey-5 text-sm px-4 py-2")
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
    ui.table(columns=columns, rows=rows, row_key="name").classes("w-full").props("flat wrap-cells")


def _physical_assets_section(summary: NetWorthSummary) -> None:
    """Renders the physical assets card with CRUD controls. All dialogs pre-created at render."""

    type_options = _asset_type_label()
    editing: dict[str, Any] = {"id": None, "snapshot": None}

    @ui.refreshable
    def assets_ui() -> None:
        if not summary.physical_assets:
            ui.label(t("net_worth.no_assets")).classes("text-grey-5 text-sm px-4 py-2")
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

        table = ui.table(columns=columns, rows=rows, row_key="id").classes("w-full").props("flat")
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
            async with AsyncSessionFactory() as session:
                asset = await AssetService(session).create(
                    AssetCreate(
                        name=add_name.value or "",
                        type=AssetType(add_type.value),
                        value=Decimal(str(add_value.value or 0)),
                        description=add_desc.value or "",
                    )
                )
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
            async with AsyncSessionFactory() as session:
                updated = await AssetService(session).update(
                    editing["id"],
                    AssetUpdate(
                        name=edit_name.value or snap.name,
                        type=AssetType(edit_type.value),
                        value=Decimal(str(edit_value.value or 0)),
                        description=edit_desc.value,
                    ),
                )
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
        ui.label(t("net_worth.cannot_undo")).classes("text-sm text-grey-6 mt-1")

        async def _del_confirm() -> None:
            async with AsyncSessionFactory() as session:
                await AssetService(session).delete(editing["id"])
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
        "flat color=primary"
    ).classes("mx-4 mb-2")


def register() -> None:
    @ui.page("/net-worth")
    async def net_worth_page() -> None:
        dark: bool = app.storage.user.get("dark_mode", False)
        default_currency: str = app.storage.user.get("currency", "PLN")

        async with AsyncSessionFactory() as session:
            summary = await NetWorthService(session).get_summary(
                history_months=13,
                default_currency=default_currency,
            )

        with page_layout(t("net_worth.title")):
            # ── Header strip: big net-worth number + delta pills ──────────────
            _header_strip(summary, default_currency)

            # ── Physical assets ───────────────────────────────────────────────
            with ui.card().classes("w-full p-0 overflow-hidden"):
                with ui.row().classes("items-center gap-2 px-4 py-3 border-b"):
                    ui.icon("home", color="primary").classes("text-xl")
                    ui.label(t("net_worth.physical_assets")).classes("text-lg font-semibold flex-1")
                    ui.label(_fmt(summary.total_physical_assets, default_currency)).classes(
                        "font-bold text-primary text-sm"
                    )
                _physical_assets_section(summary)

            # ── Stacked trend chart ───────────────────────────────────────────
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center px-4 pt-4 pb-2"):
                    ui.icon("show_chart").classes("text-primary text-xl")
                    ui.label(t("net_worth.history")).classes("text-lg font-semibold ml-2")
                _chart(summary, dark)

            # ── Assets / Liabilities two-column split ─────────────────────────
            with ui.row().classes("w-full gap-4 flex-wrap"):
                # Assets (left)
                with ui.card().classes("flex-1 min-w-80 p-0 overflow-hidden"):
                    with ui.row().classes("items-center gap-2 px-4 py-3 border-b"):
                        ui.icon("trending_up", color="positive").classes("text-xl")
                        ui.label(t("net_worth.assets")).classes("text-lg font-semibold flex-1")
                        ui.label(_fmt(summary.total_assets, default_currency)).classes(
                            "font-bold text-positive text-sm"
                        )
                    _account_table(summary.accounts, assets=True, default_currency=default_currency)

                # Liabilities (right)
                with ui.card().classes("flex-1 min-w-80 p-0 overflow-hidden"):
                    with ui.row().classes("items-center gap-2 px-4 py-3 border-b"):
                        ui.icon("trending_down", color="negative").classes("text-xl")
                        ui.label(t("net_worth.liabilities")).classes("text-lg font-semibold flex-1")
                        ui.label(_fmt(summary.total_liabilities, default_currency)).classes(
                            "font-bold text-negative text-sm"
                        )
                    _account_table(
                        summary.accounts, assets=False, default_currency=default_currency
                    )
