# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget realization table — the six-column grid artboard `2b` draws.

One paper card: a header rule, a row per category, and a Total row under a
rule a shade stronger. Five of the six columns are figures, so the grid is
fixed-width from the right and only the category name is elastic.
"""

from __future__ import annotations

from decimal import Decimal

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.budget_service import (
    CategoryRealization,
    RealizationNote,
    RealizationNoteKind,
    RealizationStatus,
)
from kaleta.views.budgets.constants import PACE_FILL, STATUS_LABEL_KEY
from kaleta.views.budgets.helpers import fmt_pct
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    AMOUNT_WARNING,
    INK,
    INK_2,
    MONO,
    REALIZATION_GRID,
    REALIZATION_GROUP,
    REALIZATION_HEAD,
    REALIZATION_NOTE,
    REALIZATION_ROW,
    REALIZATION_TOTAL,
    STAT_CARD,
    STAT_CARD_FIGURE,
)

#: The colour a percentage is set in, by the same threshold the bar is filled
#: with — so the figure and the bar never disagree.
_PCT_TONE = {
    "on_track": AMOUNT_INCOME,
    "warning": AMOUNT_WARNING,
    "over": AMOUNT_EXPENSE,
}


def note_text(note: RealizationNote) -> str:
    """The one line under a pace bar, in the month's own words."""
    when = f"{note.date.day:02d}.{note.date.month:02d}"
    if note.kind == RealizationNoteKind.PAID_IN_FULL:
        return t("budgets.realization.note_paid_in_full", date=when)
    return t(
        "budgets.realization.note_planned_on",
        amount=f"{note.amount:,.2f}",
        date=when,
    )


def render_pace_bar(row: CategoryRealization) -> None:
    """A track filled to what was spent, with a tick where the month stands.

    The status word said "Warning" and left the reader to guess against what.
    The tick is that "what": past it means the money is going out faster than
    the days are.
    """
    filled = min(max(row.used_pct, 0.0), 100.0)
    tick = min(max(row.elapsed_pct, 0.0), 100.0)
    with ui.element("div").classes("k-pace w-full") as bar:
        ui.element("div").classes("k-pace__fill").style(
            f"width:{filled:.2f}%;background:{PACE_FILL[row.status]}"
        )
        ui.element("div").classes("k-pace__tick").style(f"left:{tick:.2f}%")
    # The status kept its words; they moved to where they explain the bar.
    bar.tooltip(
        f"{t(STATUS_LABEL_KEY[row.status])} · "
        f"{t('budgets.realization.elapsed_hint', pct=f'{row.elapsed_pct:.0f}')}"
    )


def render_realization_row(row: CategoryRealization) -> None:
    remaining_cls = AMOUNT_EXPENSE if row.remaining < 0 else INK_2
    with ui.element("div").classes(REALIZATION_ROW):
        with ui.column().classes("gap-0 min-w-0"):
            ui.label(row.category_name).classes(f"{INK} font-medium truncate")
            if row.parent_name:
                ui.label(row.parent_name).classes(REALIZATION_NOTE)
        ui.label(f"{row.planned:,.2f}").classes(f"{MONO} {INK_2} text-right")
        ui.label(f"{row.actual:,.2f}").classes(f"{MONO} {INK} font-medium text-right")
        ui.label(f"{row.remaining:,.2f}").classes(f"{MONO} {remaining_cls} text-right")
        ui.label(fmt_pct(row.used_pct)).classes(
            f"{_PCT_TONE[row.status.value]} text-right text-[13.5px]"
        )
        # The bar's own column, indented from the figures: the artboard pushes
        # it 22px clear so the track never reads as another number's cell.
        with ui.column().classes("gap-1 min-w-0 pl-[22px]"):
            render_pace_bar(row)
            if row.note is not None:
                # The line wraps rather than truncating: "Opłacone w całości
                # 01.09 — zgodnie z planem" does not fit one 178px line, and a
                # half-shown explanation explains nothing.
                ui.label(note_text(row.note)).classes(f"{REALIZATION_NOTE} leading-tight")


def render_realization_header(elapsed_pct: float) -> None:
    with ui.element("div").classes(REALIZATION_HEAD):
        ui.label(t("budgets.realization.col_category"))
        ui.label(t("budgets.realization.col_planned")).classes("text-right")
        ui.label(t("budgets.realization.col_actual")).classes("text-right")
        ui.label(t("budgets.realization.col_remaining")).classes("text-right")
        ui.label(t("budgets.realization.col_used_pct")).classes("text-right")
        # The column says what the tick on every bar under it means, which is
        # the only place on the screen that can say it once.
        ui.label(t("budgets.realization.col_pace_vs", pct=f"{elapsed_pct:.0f}")).classes(
            "pl-[22px]"
        )


def render_realization_total(rows: list[CategoryRealization]) -> None:
    """The month added up, on the row artboard `2b` closes the card with."""
    planned = sum((r.planned for r in rows), Decimal("0"))
    actual = sum((r.actual for r in rows), Decimal("0"))
    remaining = planned - actual
    used = float(actual / planned * 100) if planned else 0.0
    with ui.element("div").classes(REALIZATION_TOTAL):
        ui.label(t("budgets.realization.total"))
        ui.label(f"{planned:,.2f}").classes(f"{MONO} text-right")
        ui.label(f"{actual:,.2f}").classes(f"{MONO} text-right")
        ui.label(f"{remaining:,.2f}").classes(
            f"text-right {AMOUNT_EXPENSE if remaining < 0 else AMOUNT_INCOME}"
        )
        ui.label(fmt_pct(used)).classes(f"{MONO} text-right")
        ui.element("span")


def render_realization_stats(rows: list[CategoryRealization]) -> None:
    """The four cards artboard `2b` opens with: Planned, Actual, Remaining, Used.

    The same four figures the Total row closes the table with — the reader
    should not have to scroll past forty categories to learn whether the
    month is inside its plan.
    """
    planned = sum((r.planned for r in rows), Decimal("0"))
    actual = sum((r.actual for r in rows), Decimal("0"))
    remaining = planned - actual
    used = float(actual / planned * 100) if planned else 0.0
    over = sum(1 for r in rows if r.status is RealizationStatus.OVER)
    with ui.row().classes("w-full gap-5 no-wrap"):
        _stat(t("budgets.realization.col_planned"), f"{planned:,.2f}", INK)
        _stat(t("budgets.realization.col_actual"), f"{actual:,.2f}", INK)
        _stat(
            t("budgets.realization.col_remaining"),
            f"{remaining:,.2f}",
            AMOUNT_EXPENSE if remaining < 0 else AMOUNT_INCOME,
        )
        _stat(
            t("budgets.realization.used_of_over", over=over, total=len(rows)),
            fmt_pct(used),
            AMOUNT_EXPENSE if over else INK,
        )


def _stat(label: str, figure: str, tone: str) -> None:
    with ui.column().classes(f"{STAT_CARD} gap-0"):
        ui.label(label).classes("k-eyebrow")
        ui.label(figure).classes(f"{STAT_CARD_FIGURE} {tone}")


def render_realization_flat(rows: list[CategoryRealization]) -> None:
    with ui.element("div").classes(REALIZATION_GRID):
        render_realization_header(rows[0].elapsed_pct if rows else 0.0)
        for row in rows:
            render_realization_row(row)
        render_realization_total(rows)


def render_realization_grouped(rows: list[CategoryRealization]) -> None:
    groups: dict[str, list[CategoryRealization]] = {}
    for row in rows:
        key = row.parent_name or row.category_name
        groups.setdefault(key, []).append(row)

    with ui.element("div").classes(REALIZATION_GRID):
        render_realization_header(rows[0].elapsed_pct if rows else 0.0)
        for group_name, group_rows in groups.items():
            # A rule with nothing behind it: the parent names the rows under
            # it and is not itself a row you can read figures off.
            with ui.row().classes(f"{REALIZATION_GROUP} items-center gap-2"):
                ui.icon("folder", size="xs").classes("k-muted")
                ui.label(group_name).classes("k-muted k-eyebrow")
            for row in group_rows:
                render_realization_row(row)
        render_realization_total(rows)
