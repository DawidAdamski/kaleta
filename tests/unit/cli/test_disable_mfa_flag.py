# SPDX-License-Identifier: AGPL-3.0-or-later
"""`--disable-mfa` is meaningless on its own, and says so.

Covers: KAL-AUTH-018
"""

from __future__ import annotations

import io

import pytest

from kaleta import main as main_mod


def test_the_flag_alone_refuses_rather_than_starting_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whoever types this has lost their phone and is following SECURITY.md.
    Booting the app normally and saying nothing is the worst answer there is.
    """
    stderr = io.StringIO()
    monkeypatch.setattr(main_mod.sys, "argv", ["kaleta", "--disable-mfa"])
    monkeypatch.setattr(main_mod.sys, "stderr", stderr)
    monkeypatch.setattr(main_mod, "run_web", lambda: pytest.fail("the app must not start"))

    with pytest.raises(SystemExit) as exit_info:
        main_mod.main()

    assert exit_info.value.code == 2
    assert "--reset-password" in stderr.getvalue()
