"""Reusable institution avatar — logo if set, else letter circle in brand colour."""

from __future__ import annotations

from nicegui import ui

from kaleta.models.institution import Institution

_DEFAULT_COLOR = "#64748b"  # slate-500


def institution_avatar(inst: Institution | None, size: int = 32) -> None:
    """Render the avatar for *inst* at *size* pixels.

    - If ``inst.logo_path`` is set, render it as an image.
    - Otherwise render a circular badge with the first letter of the name
      coloured with ``inst.color`` (or a neutral slate fallback).
    - If ``inst`` is ``None``, render an empty slot of matching size.
    """
    if inst is None:
        ui.element("div").style(f"width:{size}px;height:{size}px;flex:0 0 {size}px")
        return

    if inst.logo_path:
        ui.image(inst.logo_path).classes("rounded-lg object-contain bg-white").style(
            f"width:{size}px;height:{size}px;flex:0 0 {size}px"
        )
        return

    color = inst.color or _DEFAULT_COLOR
    letter = (inst.name[:1] or "?").upper()
    font_size = max(11, int(size * 0.45))
    with (
        ui.element("div")
        .classes(
            "flex items-center justify-center rounded-full font-semibold text-white select-none"
        )
        .style(
            f"width:{size}px;height:{size}px;flex:0 0 {size}px;"
            f"background:{color};font-size:{font_size}px"
        )
    ):
        ui.label(letter)
