"""Budget plan view constants — column styles and month labels."""

from __future__ import annotations

from kaleta.i18n import t

# Flex-based column styles — month columns grow to fill available width
S_CAT = "flex: 0 0 175px; min-width: 0; overflow: hidden"
S_REC = "flex: 0 0 82px"
S_MON = "flex: 1 1 55px; min-width: 52px"
S_TOT = "flex: 0 0 90px"
S_ACT = "flex: 0 0 76px"
INNER_MIN = "min-width: 1020px; width: 100%"


def month_labels() -> list[str]:
    return [
        t("budget_plan.jan"),
        t("budget_plan.feb"),
        t("budget_plan.mar"),
        t("budget_plan.apr"),
        t("budget_plan.may"),
        t("budget_plan.jun"),
        t("budget_plan.jul"),
        t("budget_plan.aug"),
        t("budget_plan.sep"),
        t("budget_plan.oct"),
        t("budget_plan.nov"),
        t("budget_plan.dec"),
    ]


def month_options() -> dict[int, str]:
    labels = month_labels()
    return {month: labels[month - 1] for month in range(1, 13)}
