# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bank profile selector for the active queued file."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.import_view.constants import _PROFILES
from kaleta.views.theme import BODY_MUTED, FORMAT_CHIP, FORMAT_CHIP_ON, SECTION_CARD, SECTION_TITLE


@dataclass
class ProfileSection:
    buttons: dict[str, ui.button]

    def set_active_profile(self, profile: str | None) -> None:
        for key, btn in self.buttons.items():
            if profile is not None and profile == key:
                btn.classes(add=FORMAT_CHIP_ON)
            else:
                btn.classes(remove=FORMAT_CHIP_ON)


def build_profile_section(
    on_select: Callable[[str], Awaitable[None]],
) -> ProfileSection:
    with ui.card().classes(f"{SECTION_CARD} gap-0"):
        ui.label(t("import.profile_label")).classes(f"{SECTION_TITLE} mb-3")
        buttons: dict[str, ui.button] = {}
        with ui.row().classes("gap-3 flex-wrap"):
            for profile_key, label_key, icon, enabled in _PROFILES:
                # `color=None`: Quasar's colour helpers are `!important`, and
                # NiceGUI defaults a button to `primary` — a chip that cannot
                # be given the sand palette's own ink otherwise.
                btn = ui.button(
                    t(label_key),
                    icon=icon,
                    on_click=lambda k=profile_key: on_select(k),
                    color=None,
                ).props("flat no-caps dense")
                btn.classes(FORMAT_CHIP)
                if not enabled:
                    btn.props("disable")
                    btn.tooltip(t("import.profile_coming_soon"))
                buttons[profile_key] = btn
        with ui.column().classes("gap-0.5 mt-3"):
            ui.label(t("import.profile_generic_help")).classes(BODY_MUTED)
            ui.label(t("import.profile_mbank_help")).classes(BODY_MUTED)
            ui.label(t("import.profile_wise_help")).classes(BODY_MUTED)
    return ProfileSection(buttons=buttons)
