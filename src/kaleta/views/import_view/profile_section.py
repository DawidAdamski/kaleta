# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bank profile selector for the active queued file."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.import_view.constants import _PROFILES


@dataclass
class ProfileSection:
    buttons: dict[str, ui.button]

    def set_active_profile(self, profile: str | None) -> None:
        for key, btn in self.buttons.items():
            is_active = profile is not None and profile == key
            btn.props("color=primary unelevated" if is_active else "color=grey-4 flat")


def build_profile_section(
    on_select: Callable[[str], Awaitable[None]],
) -> ProfileSection:
    with ui.card().classes("w-full"):
        ui.label(t("import.profile_label")).classes(
            "text-sm text-slate-500 font-medium uppercase tracking-wide mb-3"
        )
        buttons: dict[str, ui.button] = {}
        with ui.row().classes("gap-3 flex-wrap"):
            for profile_key, label_key, icon, enabled in _PROFILES:
                btn = ui.button(
                    t(label_key),
                    icon=icon,
                    on_click=lambda k=profile_key: on_select(k),
                ).props("color=grey-4 flat")
                if not enabled:
                    btn.props("disable")
                    btn.tooltip(t("import.profile_coming_soon"))
                buttons[profile_key] = btn
    return ProfileSection(buttons=buttons)
