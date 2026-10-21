# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-process ports for the e2e servers, so parallel runs never collide.

Every e2e server used to bind a fixed port (8081-8089). Two ``verify.sh --e2e``
runs on one machine then fought over those ports: ``_wait_for_server`` accepts
whichever instance answers, so the second run logged in to the first run's app
and ~200 tests failed (see ``docs/plans/chores.md``). Each pytest process now
picks its own free ports instead, which makes concurrent runs independent (one
worktree per lane in goal-mode parallel work).

This lives in its own module, not in ``conftest.py``, because ``conftest``
imports ``seed_helpers`` and ``seed_helpers`` needs the main port too — a single
small module both can import avoids the cycle.
"""

from __future__ import annotations

import socket


def pick_free_port() -> int:
    """Return an OS-assigned free TCP port on the loopback interface.

    The socket is closed before returning, so there is a tiny window in which
    another process could claim the port; with ephemeral ports and a handful of
    concurrent runs the odds are negligible, and ``_wait_for_server`` fails
    loudly if the app never comes up on it.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


#: The main shared e2e server's port — one per pytest process. Imported by
#: ``conftest`` (the app it spawns) and ``seed_helpers`` (the API base it calls).
E2E_PORT = pick_free_port()
