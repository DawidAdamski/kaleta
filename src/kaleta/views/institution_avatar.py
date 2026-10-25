# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reusable institution avatar — logo if set, else letter circle in brand colour."""

from __future__ import annotations

from nicegui import ui

from kaleta.schemas.institution import InstitutionResponse

# Reads the token at render time, so it cannot drift from theme.py.
_DEFAULT_COLOR = "var(--k-muted)"


def logo_url(inst: InstitutionResponse) -> str:
    """The serving-route URL for *inst*'s logo, stamped with ``updated_at`` so a
    replaced logo busts the browser cache (the route ignores the query)."""
    return f"/api/v1/institutions/{inst.id}/logo?v={int(inst.updated_at.timestamp())}"


def institution_avatar(inst: InstitutionResponse | None, size: int = 32) -> None:
    """Render the avatar for *inst* at *size* pixels.

    - If ``inst.has_logo``, render the logo image from ``GET
      /api/v1/institutions/{id}/logo`` over a letter-circle underlay, so a
      failed load (a 404, a transient error) degrades to the brand badge
      instead of a broken-image icon.
    - Otherwise render just the circular badge with the first letter of the
      name coloured with ``inst.color`` (or the muted token as a fallback).
    - If ``inst`` is ``None``, render an empty slot of matching size.
    """
    if inst is None:
        ui.element("div").style(f"width:{size}px;height:{size}px;flex:0 0 {size}px")
        return

    color = inst.color or _DEFAULT_COLOR
    letter = (inst.name[:1] or "?").upper()
    font_size = max(11, int(size * 0.45))
    with ui.element("div").style(
        f"position:relative;width:{size}px;height:{size}px;flex:0 0 {size}px"
    ):
        # Letter-circle underlay — always rendered, covered by the logo when it loads.
        with (
            ui.element("div")
            .classes(
                "absolute inset-0 flex items-center justify-center rounded-full "
                "font-semibold text-white select-none"
            )
            .style(f"background:{color};font-size:{font_size}px")
        ):
            ui.label(letter)
        if inst.has_logo:
            image = (
                ui.image(logo_url(inst))
                .classes("absolute inset-0 rounded-lg object-contain bg-white")
                .style("width:100%;height:100%")
            )
            # On a load error, hide the image to reveal the circle beneath.
            image.on("error", lambda _: image.set_visibility(False))
