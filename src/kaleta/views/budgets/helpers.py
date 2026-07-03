"""Budgets view presentation helpers."""

from __future__ import annotations

from kaleta.i18n import t
from kaleta.services.budget_service import format_date_range_label


def range_options() -> dict[str, str]:
    return {
        "this_month": t("budgets.this_month"),
        "last_month": t("budgets.last_month"),
        "this_quarter": t("budgets.this_quarter"),
        "last_quarter": t("budgets.last_quarter"),
        "this_year": t("budgets.this_year"),
        "last_year": t("budgets.last_year"),
        "last_30_days": t("budgets.last_30_days"),
        "last_60_days": t("budgets.last_60_days"),
        "last_90_days": t("budgets.last_90_days"),
        "last_5_years": t("budgets.last_5_years"),
    }


def range_label(key: str) -> str:
    return format_date_range_label(key)


def fmt_pct(value: float) -> str:
    if value == float("inf"):
        return "∞"
    return f"{value:.0f}%"
