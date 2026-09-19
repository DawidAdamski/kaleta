# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared rendering helpers for dashboard widgets."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.report_service import KpiPeriodDelta
from kaleta.views.theme import (
    CARD_SUBTITLE,
    CARD_TITLE,
    DASH_CARD,
    KPI_TREND_NEGATIVE,
    KPI_TREND_NEUTRAL,
    KPI_TREND_POSITIVE,
    KPI_VALUE,
    MUTED_STRONG,
    SECTION_TITLE,
    kpi_card_classes,
)


def fmt_amount(amount: Decimal | float | int) -> str:
    return f"{float(amount):,.2f} zł"


def fmt_number(amount: Decimal | float | int) -> str:
    """The same figure without its currency suffix.

    Cards that label a whole column "zł" repeat the suffix on every row for
    nothing. Derived from :func:`fmt_amount` so the two cannot drift apart if
    the currency or the thousands separator ever changes.
    """
    return fmt_amount(amount).removesuffix(" zł")


def _month_short_name(month: int) -> str:
    return t(f"common.month_short_{month}")


def _format_reference(delta: KpiPeriodDelta) -> str:
    if delta.reference_date is not None:
        d = delta.reference_date
        return t(
            "dashboard_widgets.kpi_vs_date",
            day=d.day,
            month=_month_short_name(d.month),
            year=d.year,
        )
    if delta.reference_year is not None and delta.reference_month is not None:
        return t(
            "dashboard_widgets.kpi_vs_month",
            month=_month_short_name(delta.reference_month),
            year=delta.reference_year,
        )
    return ""


def trend_class(delta: KpiPeriodDelta, *, is_rate: bool = False) -> str:
    """Token class colouring a trend line up / down / flat."""
    value = delta.rate_points if is_rate else delta.absolute
    if value is None or value == Decimal("0"):
        return KPI_TREND_NEUTRAL
    return KPI_TREND_POSITIVE if value > 0 else KPI_TREND_NEGATIVE


def format_kpi_trend(delta: KpiPeriodDelta | None, *, is_rate: bool = False) -> str:
    """Render trend row text; em-dash when comparison unavailable."""
    if delta is None or not delta.available:
        return "—"

    ref = _format_reference(delta)
    if is_rate:
        if delta.rate_points is None:
            return "—"
        pts = delta.rate_points
        sign = "+" if pts > 0 else ""
        body = t("dashboard_widgets.kpi_rate_points", sign=sign, value=f"{pts:.1f}")
        return f"{body} {ref}".strip() if ref else body

    if delta.absolute is None:
        return "—"

    abs_val = delta.absolute
    arrow = "▲" if abs_val > 0 else ("▼" if abs_val < 0 else "")
    sign = "+" if abs_val > 0 else ""
    amount_part = fmt_amount(abs(abs_val))
    parts = [f"{arrow} {sign}{amount_part}".strip()]
    if delta.percent is not None and delta.percent != Decimal("0"):
        pct_sign = "+" if delta.percent > 0 else ""
        parts[0] = f"{parts[0]} ({pct_sign}{delta.percent:.2f}%)"
    if ref:
        parts.append(ref)
    return " ".join(parts)


def kpi_card(
    title: str,
    value: str,
    icon: str,
    icon_color: str,
    extra_cls: str = "",
    delta: KpiPeriodDelta | None = None,
    *,
    is_rate: bool = False,
    hide_trend: bool = False,
) -> None:
    with ui.card().classes(kpi_card_classes()), ui.row().classes("items-center gap-4 w-full"):
        hue = icon_color.split("-")[0]
        with ui.element("div").classes(
            f"h-10 w-10 rounded-xl bg-{hue}-500/10 text-{hue}-600 "
            "flex items-center justify-center shrink-0"
        ):
            ui.icon(icon, size="1.6rem")
        with ui.column().classes("gap-1 min-w-0 flex-1"):
            ui.label(title).classes(SECTION_TITLE)
            ui.label(value).classes(f"{KPI_VALUE} {extra_cls}")
            if hide_trend:
                trend_text = "—"
                trend_cls = KPI_TREND_NEUTRAL
            else:
                trend_text = format_kpi_trend(delta, is_rate=is_rate)
                trend_cls = trend_class(delta, is_rate=is_rate) if delta else KPI_TREND_NEUTRAL
            ui.label(trend_text).classes(f"text-xs kpi-trend {trend_cls}")


def section_card(title: str, *, subtitle: str | None = None) -> Any:
    card = ui.card().classes(DASH_CARD)
    with card:
        ui.label(title).classes(CARD_TITLE)
        if subtitle:
            ui.label(subtitle).classes(f"{CARD_SUBTITLE} mb-3")
        else:
            ui.element("div").classes("mb-2")
    return card


def split_amount(amount: Decimal | float | int) -> tuple[str, str]:
    """Split a formatted amount into (whole, fraction) for the hero treatment.

    Derived from :func:`fmt_amount` so the two cannot drift: the hero reads
    the same string every other figure on the page does, then peels off the
    decimal group. ``64,648.01 zł`` → ``("64,648", ".01")``.
    """
    numeric = fmt_number(amount)
    whole, sep, frac = numeric.rpartition(".")
    return (whole, sep + frac) if sep else (numeric, "")


def hero_figure(amount: Decimal | float | int, *, size: str = "text-[54px]") -> None:
    """Hero amount with its decimals muted, per the handoff type scale.

    The split is what keeps a 54px figure from shouting its cents.
    """
    whole, frac = split_amount(amount)
    base = f"{size} font-medium tracking-[-.035em] leading-none"
    with ui.row().classes("items-baseline gap-0 no-wrap"):
        ui.label(whole).classes(f"k-mono k-ink {base}")
        if frac:
            # `--k-muted-strong`, the warmer of the two: the artboards use it
            # wherever muted type sits inside a figure rather than beside one.
            ui.label(frac).classes(f"k-mono {MUTED_STRONG} {base}")


def mini_stat(label: str, value: str, amount_cls: str) -> None:
    """Label over a figure — ``amount_cls`` is a theme amount token, not a hue."""
    with ui.column().classes("gap-0.5 min-w-28"):
        ui.label(label).classes(CARD_SUBTITLE)
        ui.label(value).classes(f"k-mono {amount_cls} text-[19px] font-medium tracking-tight")


def quick_btn(icon: str, label: str, route: str) -> None:
    ui.button(label, icon=icon, on_click=lambda r=route: ui.navigate.to(r)).props(
        "flat color=primary"
    ).classes("flex-1 min-w-40")
