# SPDX-License-Identifier: AGPL-3.0-or-later
"""The data passphrase a script needs while ``KALETA_ENCRYPTION=passphrase``.

Scripts run without a browser session, so nothing has unlocked the database
for them. They are given the passphrase of any local key holder — from
``KALETA_DATA_PASSPHRASE`` (cron, CI) or a prompt — and work under the data
key it opens. Imported by the scripts next to it (their directory is first on
``sys.path`` when they run).
"""

from __future__ import annotations

import getpass
import os
import sys

PASSPHRASE_ENV = "KALETA_DATA_PASSPHRASE"


def data_passphrase(prompt: str = "Data passphrase: ") -> str:
    value = os.environ.get(PASSPHRASE_ENV)
    if value:
        return value
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    msg = f"[ERROR] Encryption is on: set {PASSPHRASE_ENV} or run the script in a terminal."
    raise SystemExit(msg)
