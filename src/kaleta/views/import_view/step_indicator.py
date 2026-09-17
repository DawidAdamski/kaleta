# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wizard progress line for the import page (artboard 2d)."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.theme import (
    STEP_LABEL,
    STEP_LABEL_NOW,
    STEP_LINE,
    STEP_NODE,
    STEP_NODE_DONE,
    STEP_NODE_NOW,
    STEP_NODE_READING,
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


def render_step_indicator(
    current: int,
    *,
    viewed: int | None = None,
    on_step: Callable[[int], None] | None = None,
    steps: tuple[int, ...] | None = None,
) -> None:
    """Six nodes on a hairline: done, the one you are on, and the rest.

    Six numbered pills separated by arrows told the reader how many steps
    there are and nothing about where they stood. A done step is a filled
    ink circle with a tick, the current one is filled accent and keeps its
    number, and the rest are outlines — which is the whole state of the
    wizard at a glance.

    ``current`` is where the *work* is (``state.current_step``); ``viewed``
    is the step on screen, which is behind it whenever the reader has walked
    back. The line marks the work and rings the step being read, so a reader
    three steps back can still see what the file is waiting on. Every node up
    to ``current`` calls ``on_step`` — how far you may walk is where the work
    has got to, and a wizard you can only walk forward through is one you
    restart to fix a typo.

    ``steps`` is the steps you may stand on — the ones this file has *and*
    has reached. A bank profile's mapping node is drawn and ticked, because
    the columns *were* mapped, but it is not a step you can stand on, so it
    is not a link either; nor is a card the active file cannot show.
    """
    # No default: a line drawn without a step would have to invent one, and
    # the invented one disagreed with ``current_step(None)``.
    labels = _step_labels()
    here = current if viewed is None else viewed
    with ui.row().classes(f"{STEP_LINE} w-full items-start gap-0 mb-3 no-wrap"):
        for index, label in enumerate(labels, start=1):
            done = index < current
            now = index == current
            reading = index == here
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
                if reading and not now:
                    node.classes(add=STEP_NODE_READING)
                ui.label(label).classes(STEP_LABEL_NOW if reading else STEP_LABEL)
            step.props["data-step"] = str(index)
            if now:
                # On the element that carries both the node and its label,
                # which together are the step.
                step.props["aria-current"] = "step"
            walkable = index <= current if steps is None else index in steps
            if on_step is not None and walkable:
                # A link by keyboard as well as by mouse: the node is not a
                # `q-btn`, so the role, the stop on the tab order and the
                # two keys a button answers to are all its own.
                step.classes(add="cursor-pointer")
                step.props["role"] = "button"
                step.props["tabindex"] = "0"
                step.on("click", lambda _e=None, i=index: on_step(i))
                step.on("keydown.enter", lambda _e=None, i=index: on_step(i))
                step.on("keydown.space.prevent", lambda _e=None, i=index: on_step(i))
