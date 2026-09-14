# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wizard progress line for the import page (artboard 2d)."""

from __future__ import annotations

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.theme import (
    STEP_LABEL,
    STEP_LABEL_NOW,
    STEP_LINE,
    STEP_NODE,
    STEP_NODE_DONE,
    STEP_NODE_NOW,
)


def _step_labels() -> list[str]:
    return [
        t("import.step_format"),
        t("import.step_upload"),
        t("import.step_mapping"),
        t("import.step_settings"),
        t("import.step_preview"),
        t("import.step_confirm"),
    ]


def render_step_indicator(current: int) -> None:
    """Six nodes on a hairline: done, the one you are on, and the rest.

    Six numbered pills separated by arrows told the reader how many steps
    there are and nothing about where they stood. A done step is a filled
    ink circle with a tick, the current one is filled accent and keeps its
    number, and the rest are outlines — which is the whole state of the
    wizard at a glance.
    """
    # No default: a line drawn without a step would have to invent one, and
    # the invented one disagreed with ``current_step(None)``.
    labels = _step_labels()
    with ui.row().classes(f"{STEP_LINE} w-full items-start gap-0 mb-3 no-wrap"):
        for index, label in enumerate(labels, start=1):
            done = index < current
            now = index == current
            with ui.column().classes("items-center gap-1 flex-1 min-w-0") as step:
                node = ui.element("div").classes(STEP_NODE)
                # The node holds a number or a tick; the label is its sibling,
                # so without this a screen reader announces "3" where the
                # screen says "Column mapping".
                node.props["aria-label"] = label
                if done:
                    node.classes(add=STEP_NODE_DONE)
                    with node:
                        ui.icon("check", size="13px")
                elif now:
                    node.classes(add=STEP_NODE_NOW)
                    with node:
                        ui.label(str(index))
                else:
                    with node:
                        ui.label(str(index))
                ui.label(label).classes(STEP_LABEL_NOW if now else STEP_LABEL)
            if now:
                # On the element that carries both the node and its label,
                # which together are the step.
                step.props["aria-current"] = "step"
