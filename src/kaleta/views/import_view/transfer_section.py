# SPDX-License-Identifier: AGPL-3.0-or-later
"""Suggested transfer pairs, reviewed once the import has run."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.components.amount_label import spaced_thousands
from kaleta.views.theme import AMOUNT_NEUTRAL, BODY_MUTED, CARD_TITLE, SECTION_CARD

if TYPE_CHECKING:  # import-linter excludes typing-only imports
    from kaleta.services.import_service import TransferPairSuggestion

PairAction = Callable[["TransferPairSuggestion"], Awaitable[None]]


@dataclass
class TransferSection:
    card: ui.card
    pairs: ui.column
    result_label: ui.label
    accept_all_btn: ui.button

    def set_visible(self, visible: bool) -> None:
        self.card.set_visibility(visible)

    def set_result(self, message: str) -> None:
        self.result_label.set_text(message)

    def render(
        self,
        suggestions: list[TransferPairSuggestion],
        *,
        on_accept: PairAction,
        on_dismiss: PairAction,
    ) -> None:
        """One line per pair — both legs, the amount — with its own two answers."""
        self.pairs.clear()
        self.accept_all_btn.set_visibility(bool(suggestions))
        with self.pairs:
            if not suggestions:
                ui.label(t("import.transfer_pairs_empty")).classes(BODY_MUTED)
                return
            for suggestion in suggestions:
                self._render_pair(suggestion, on_accept=on_accept, on_dismiss=on_dismiss)

    @staticmethod
    def _render_pair(
        suggestion: TransferPairSuggestion,
        *,
        on_accept: PairAction,
        on_dismiss: PairAction,
    ) -> None:
        with (
            ui.row()
            .classes("w-full items-center gap-3 py-1")
            .props(f'data-transfer-pair="{suggestion.outgoing_id}-{suggestion.incoming_id}"')
        ):
            with ui.column().classes("gap-0 flex-1 min-w-0"):
                ui.label(f"{suggestion.outgoing_account} → {suggestion.incoming_account}").classes(
                    "text-sm font-medium"
                )
                ui.label(
                    f"{suggestion.outgoing_date.isoformat()} · "
                    f"{suggestion.outgoing_description or '—'}  /  "
                    f"{suggestion.incoming_date.isoformat()} · "
                    f"{suggestion.incoming_description or '—'}"
                ).classes(f"{BODY_MUTED} text-xs truncate")
            # A transfer is neither money in nor money out: the ledger's
            # neutral tone, not the income green or the expense red.
            ui.label(
                f"{spaced_thousands(f'{suggestion.amount:,.2f}')} {suggestion.currency}"
            ).classes(f"{AMOUNT_NEUTRAL} text-sm")
            ui.button(
                t("import.transfer_pair_accept"),
                icon="link",
                on_click=lambda s=suggestion: on_accept(s),
            ).props("flat dense no-caps color=primary data-transfer-accept")
            ui.button(
                t("import.transfer_pair_dismiss"),
                icon="close",
                on_click=lambda s=suggestion: on_dismiss(s),
            ).props("flat dense no-caps color=grey data-transfer-dismiss")


def build_transfer_section(
    on_accept_all: Callable[[], Awaitable[None]],
) -> TransferSection:
    card = ui.card().classes(f"{SECTION_CARD} gap-0").props("data-transfer-section")
    card.set_visibility(False)
    with card:
        ui.label(t("import.transfer_section")).classes(CARD_TITLE)
        ui.label(t("import.transfer_hint")).classes(f"{BODY_MUTED} mb-3")
        pairs = ui.column().classes("w-full gap-0")
        result_label = ui.label("").classes("text-sm k-trend--pos")
        accept_all_btn = ui.button(
            t("import.detect_transfers"),
            icon="compare_arrows",
            on_click=on_accept_all,
        ).props("outline no-caps color=primary data-transfer-accept-all")
    return TransferSection(
        card=card,
        pairs=pairs,
        result_label=result_label,
        accept_all_btn=accept_all_btn,
    )
