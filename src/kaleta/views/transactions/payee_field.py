# SPDX-License-Identifier: AGPL-3.0-or-later
"""The payee combobox shared by the add and edit transaction dialogs."""

from __future__ import annotations

from nicegui import ui

from kaleta.i18n import t


def build_payee_select(payee_options: dict[int, str]) -> ui.select:
    """A searchable payee picker that also accepts a name that does not exist yet."""
    return (
        ui.select(
            # Copied: ``new_value_mode`` mutates the options dict in place, and
            # the page hands the same dict to both dialogs.
            dict(payee_options),
            label=f"{t('transactions.payee_field')} ({t('common.optional')})",
            value=None,
            new_value_mode="add-unique",
            key_generator=lambda name: name,
        )
        .classes("w-full")
        .props(f'clearable hint="{t("transactions.payee_hint")}"')
    )


def split_payee_value(raw: object) -> tuple[int | None, str | None]:
    """Split the combobox value into an existing payee id or a typed new name.

    ``new_value_mode`` keys a new entry by the typed text, so the widget holds an
    ``int`` for a payee that exists and a ``str`` for one the service still has
    to match or create.
    """
    if isinstance(raw, int):
        return raw, None
    if isinstance(raw, str) and raw.strip():
        return None, raw.strip()
    return None, None
