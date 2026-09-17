# SPDX-License-Identifier: AGPL-3.0-or-later
"""Internal transfer detection action (generic CSV profile)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.theme import BODY_MUTED, CARD_TITLE, SECTION_CARD


@dataclass
class TransferSection:
    card: ui.card
    result_label: ui.label

    def set_visible(self, visible: bool) -> None:
        self.card.set_visibility(visible)

    def set_result(self, message: str) -> None:
        self.result_label.set_text(message)


def build_transfer_section(
    on_detect: Callable[[], Awaitable[None]],
) -> TransferSection:
    card = ui.card().classes(f"{SECTION_CARD} gap-0")
    card.set_visibility(False)
    with card:
        ui.label(t("import.transfer_section")).classes(CARD_TITLE)
        ui.label(t("import.transfer_hint")).classes(f"{BODY_MUTED} mb-3")
        result_label = ui.label("").classes("text-sm k-trend--pos")
        ui.button(
            t("import.detect_transfers"),
            icon="compare_arrows",
            on_click=on_detect,
        ).props("outline no-caps color=primary")
    return TransferSection(card=card, result_label=result_label)
