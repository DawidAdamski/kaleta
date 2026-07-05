# SPDX-License-Identifier: AGPL-3.0-or-later
"""Empty-state helpers for tables and lists."""

from __future__ import annotations

from nicegui import ui

from kaleta.i18n import t


def table_no_data_slot(message_key: str = "transactions.no_results") -> str:
    """HTML slot content for ``ui.table`` when there are no rows."""
    return f'<div class="text-center text-grey-6 py-8">{t(message_key)}</div>'


def pagination_empty_label(message_key: str = "transactions.no_results") -> None:
    """Label shown in the pagination bar when the result set is empty."""
    ui.label(t(message_key))


def report_no_data_label(message_key: str = "reports.no_data") -> None:
    """Centered empty-state label for report pages with no rows."""
    ui.label(t(message_key)).classes("text-grey-5 py-8")
