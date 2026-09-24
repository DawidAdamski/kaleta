# SPDX-License-Identifier: AGPL-3.0-or-later
"""The log ring buffer's session resolver must not wake NiceGUI's script mode."""

from __future__ import annotations

from nicegui import Client, app, core

from kaleta.views.error_handling import current_client_id


class TestCurrentClientIdBeforeStart:
    def test_returns_none_without_creating_a_pseudo_client(self) -> None:
        """A startup handler that logs must not leave a request-less client behind.

        NiceGUI's ``prune_user_storage`` reads ``client.request`` on every
        client; the script-mode pseudo client has none, so the timer raised
        "Request is not set" every ten seconds.
        """
        assert not app.is_started
        instances_before = len(Client.instances)

        assert current_client_id() is None

        assert not core.script_mode
        assert len(Client.instances) == instances_before
