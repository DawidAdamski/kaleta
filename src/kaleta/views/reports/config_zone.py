# SPDX-License-Identifier: AGPL-3.0-or-later
"""Report builder configuration panel — drop zones and filters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.reports.constants import CHART_TYPES, DATE_PRESETS, DIMENSIONS, METRICS, TX_TYPES


def build_config_zone(
    state: dict[str, Any],
    *,
    account_options: dict[int, str],
    category_options: dict[int, str],
    on_drop_dimension: Callable[[], None],
    on_drop_metric: Callable[[], None],
    on_set_chart: Callable[[str], None],
    on_toggle_type: Callable[[str], None],
) -> Any:
    @ui.refreshable
    def config_zone() -> None:
        hdr_cls = "text-xs font-bold text-grey-6 uppercase tracking-wide mb-2"

        with ui.row().classes("gap-4 mb-4 flex-wrap"):
            dz_dim_cls = (
                "p-3 rounded-lg border-2 border-dashed min-w-40 cursor-pointer "
                "border-primary bg-primary-50"
            )
            with (
                ui.element("div")
                .classes(dz_dim_cls)
                .props('ondragover="event.preventDefault()"') as dz_dim
            ):
                dz_dim.on("drop", on_drop_dimension)
                ui.label(t("reports.group_by")).classes(hdr_cls)
                dim_label = next(
                    (t(label_key) for key, label_key, _ in DIMENSIONS if key == state["dimension"]),
                    "—",
                )
                dim_icon = next(
                    (icon for key, _, icon in DIMENSIONS if key == state["dimension"]),
                    "category",
                )
                with ui.row().classes("items-center gap-1"):
                    ui.icon(dim_icon, color="primary")
                    ui.label(dim_label).classes("font-semibold text-primary")
                ui.label(t("reports.drop_here")).classes("text-xs text-grey-5 mt-1")

            dz_met_cls = (
                "p-3 rounded-lg border-2 border-dashed min-w-40 cursor-pointer "
                "border-secondary bg-secondary-50"
            )
            with (
                ui.element("div")
                .classes(dz_met_cls)
                .props('ondragover="event.preventDefault()"') as dz_met
            ):
                dz_met.on("drop", on_drop_metric)
                ui.label(t("reports.measure")).classes(hdr_cls)
                met_label = next(
                    (t(label_key) for key, label_key, _ in METRICS if key == state["metric"]),
                    "—",
                )
                met_icon = next(
                    (icon for key, _, icon in METRICS if key == state["metric"]),
                    "functions",
                )
                with ui.row().classes("items-center gap-1"):
                    ui.icon(met_icon, color="secondary")
                    ui.label(met_label).classes("font-semibold text-secondary")
                ui.label(t("reports.drop_here")).classes("text-xs text-grey-5 mt-1")

        with ui.row().classes("items-center gap-2 mb-4 flex-wrap"):
            ui.label(t("reports.chart_type")).classes(hdr_cls + " my-0")
            for chart_type, icon in CHART_TYPES:
                active = state["chart_type"] == chart_type
                (
                    ui.button(icon=icon, on_click=lambda c=chart_type: on_set_chart(c))
                    .props(f"{'color=primary' if active else 'outline color=grey-7'} round dense")
                    .tooltip(chart_type.capitalize())
                )

        exp = ui.expansion(t("reports.filters"), icon="filter_list")
        exp.classes("w-full mb-4")
        with exp, ui.element("div").classes("flex flex-col gap-3 pt-2"):
            ui.label(t("reports.tx_types")).classes(hdr_cls)
            with ui.row().classes("gap-2"):
                for type_key, label_key, icon, color in TX_TYPES:
                    active = type_key in state["transaction_types"]
                    ui.button(
                        t(label_key),
                        icon=icon,
                        on_click=lambda k=type_key: on_toggle_type(k),
                    ).props(
                        (f"color={color}" if active else "outline color=grey-7") + " dense rounded"
                    )

            ui.label(t("reports.date_range")).classes(hdr_cls)
            preset_opts = {key: t(label_key) for key, label_key in DATE_PRESETS}
            ui.select(
                preset_opts,
                value=state["date_preset"],
                on_change=lambda e: state.update(date_preset=e.value) or config_zone.refresh(),
            ).classes("w-56")
            if state["date_preset"] == "custom":
                with ui.row().classes("gap-3"):
                    ui.input(
                        t("transactions.date_from"),
                        value=state["date_from"],
                        on_change=lambda e: state.update(date_from=e.value),
                    ).props("type=date").classes("w-44")
                    ui.input(
                        t("transactions.date_to"),
                        value=state["date_to"],
                        on_change=lambda e: state.update(date_to=e.value),
                    ).props("type=date").classes("w-44")

            ui.label(t("reports.top_n")).classes(hdr_cls)
            ui.number(
                t("reports.top_n_hint"),
                value=state["top_n"],
                min=0,
                max=100,
                step=5,
                on_change=lambda e: state.update(top_n=int(e.value or 0)),
            ).classes("w-32").props("dense")

            if account_options:
                ui.label(t("reports.filter_accounts")).classes(hdr_cls)
                ui.select(
                    account_options,
                    multiple=True,
                    value=state["account_ids"],
                    label=t("reports.all_accounts"),
                    on_change=lambda e: state.update(account_ids=e.value or []),
                ).classes("w-full").props("use-chips")

            if category_options:
                ui.label(t("reports.filter_categories")).classes(hdr_cls)
                ui.select(
                    category_options,
                    multiple=True,
                    value=state["category_ids"],
                    label=t("reports.all_categories"),
                    on_change=lambda e: state.update(category_ids=e.value or []),
                ).classes("w-full").props("use-chips")

    return config_zone
