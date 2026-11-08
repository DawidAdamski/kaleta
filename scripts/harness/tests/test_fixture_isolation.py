# SPDX-License-Identifier: AGPL-3.0-or-later
"""The harness tests do not depend on the developer's global git config (verify.sh runs them)."""

from __future__ import annotations

import os
from pathlib import Path

from conftest import make_repo

HOSTILE = """[commit]
\tgpgsign = true
[gpg]
\tprogram = /nonexistent/gpg
[core]
\thooksPath = /nonexistent/hooks
[init]
\tdefaultBranch = trunk
"""


def test_a_hostile_global_git_config_does_not_leak_in(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text(HOSTILE, encoding="utf-8")
    repo = make_repo(tmp_path, {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home)})
    repo.write("src/app.py", "X = 2\n")
    repo.commit("signed? no")  # gpgsign = true would fail here
    assert repo.git("rev-parse", "--abbrev-ref", "HEAD") == "main"
