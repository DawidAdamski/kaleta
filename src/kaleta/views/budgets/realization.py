# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget realization tab row renderers."""

from __future__ import annotations

from decimal import Decimal

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.budget_service import (
    CategoryRealization,
    RealizationNote,
    RealizationNoteKind,
)
from kaleta.views.budgets.constants import PACE_FILL, STATUS_LABEL_KEY
from kaleta.views.budgets.helpers import fmt_pct
from kaleta.views.theme import AMOUNT_EXPENSE, AMOUNT_NEUTRAL, INK, MONO, ROW_HOVER

#: The note line and the parent name share this; both are asides to the row.
_ASIDE = "k-muted text-[12px]"


def note_text(note: RealizationNote) -> str:
    """The one line under a pace bar, in the month's own words."""
    when = f"{note.date.day:02d}.{note.date.month:02d}"
    if note.kind == RealizationNoteKind.PAID_IN_FULL:
        return t("budgets.realization.note_paid_in_full", date=when)
    # PLANNED_ON always carries its amount — RealizationNote refuses to exist
    # otherwise — so the fallback below is for mypy, not for runtime.
    return t(
        "budgets.realization.note_planned_on",
        amount=f"{note.amount or Decimal(0):,.2f}",
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
    remaining_cls = AMOUNT_EXPENSE if row.remaining < 0 else AMOUNT_NEUTRAL
    with ui.row().classes(f"w-full items-start gap-3 py-2 px-3 rounded-lg {ROW_HOVER}"):
        with ui.column().classes("flex-[2] min-w-0 gap-0"):
            ui.label(row.category_name).classes(f"{INK} text-[13.5px] font-medium truncate")
            if row.parent_name:
                ui.label(row.parent_name).classes(_ASIDE)
        ui.label(f"{row.planned:,.2f}").classes(f"flex-1 text-right text-sm {AMOUNT_NEUTRAL}")
        ui.label(f"{row.actual:,.2f}").classes(
            f"flex-1 text-right text-sm font-medium {AMOUNT_NEUTRAL}"
        )
        ui.label(f"{row.remaining:,.2f}").classes(f"flex-1 text-right text-sm {remaining_cls}")
        ui.label(fmt_pct(row.used_pct)).classes(f"flex-1 text-right text-sm {MONO}")
        # pt-1.5 drops the 7px track onto the text's own line: the row aligns
        # to the top now, because a wrapped note must not shift the figures.
        with ui.column().classes("w-56 gap-1 min-w-0 pt-1.5"):
            render_pace_bar(row)
            if row.note is not None:
                # The line wraps rather than truncating: "Opłacone w całości
                # 01.09 — zgodnie z planem" does not fit one 224px line, and a
                # half-shown explanation explains nothing.
                ui.label(note_text(row.note)).classes(f"{_ASIDE} leading-tight")


def render_realization_header() -> None:
    with ui.row().classes("w-full items-center gap-3 px-3 k-muted k-eyebrow"):
        ui.label(t("budgets.realization.col_category")).classes("flex-[2]")
        ui.label(t("budgets.realization.col_planned")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_actual")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_remaining")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_used_pct")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_pace")).classes("w-56")


def render_realization_flat(rows: list[CategoryRealization]) -> None:
    render_realization_header()
    ui.separator().classes("my-1 opacity-40")
    for row in rows:
        render_realization_row(row)


def render_realization_grouped(rows: list[CategoryRealization]) -> None:
    groups: dict[str, list[CategoryRealization]] = {}
    for row in rows:
        key = row.parent_name or row.category_name
        groups.setdefault(key, []).append(row)

    render_realization_header()
    ui.separator().classes("my-1 opacity-40")
    for group_name, group_rows in groups.items():
        with ui.row().classes("w-full items-center gap-2 mt-3"):
            ui.icon("folder", size="xs").classes("k-muted")
            ui.label(group_name).classes("k-muted k-eyebrow")
        for row in group_rows:
            render_realization_row(row)
