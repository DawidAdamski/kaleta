# SPDX-License-Identifier: AGPL-3.0-or-later
"""Diffs the gate must survive and ways around it that must stay closed (ultrareview)."""

from __future__ import annotations

import contextlib
import json

import gitutil
from conftest import HarnessRepo, approve


def _reason(out) -> str:
    return json.loads(out.stdout)["reason"] if out.stdout.strip() else ""


def test_non_utf8_content_in_the_diff_does_not_crash_the_gate(repo: HarnessRepo) -> None:
    repo.new_plan()
    # a cp1250 bank export, as a test fixture might be
    (repo.root / "tests").mkdir(exist_ok=True)
    (repo.root / "tests/bank_export.csv").write_bytes(
        "Data;Opis\n2026-01-02;Zażółć gęślą\n".encode("cp1250")
    )
    repo.commit("cp1250 fixture")
    out = repo.gate()
    reason = _reason(out)
    assert "crashed" not in reason
    assert "No critic run yet" in reason


def test_git_mv_of_a_protected_file_is_vetoed(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.git("mv", "docs/harness/critic-questions.toml", "docs/questions.toml")
    repo.commit("move the questions out of the protected folder")
    approve(repo)
    repo.gate()
    assert repo.state("result") == "escalated"
    assert "docs/harness/critic-questions.toml" in (repo.state("escalated-reason") or "")


def test_a_file_moved_into_auth_is_high_risk(repo: HarnessRepo) -> None:
    repo.write("src/kaleta/util/helper.py", "def f():\n    return 1\n")
    repo.commit("helper on main")
    repo.new_plan(criteria=["- `test -f src/kaleta/auth/helper.py`"])
    (repo.root / "src/kaleta/auth").mkdir(parents=True)
    repo.git("mv", "src/kaleta/util/helper.py", "src/kaleta/auth/helper.py")
    repo.commit("move it into auth")
    with contextlib.chdir(repo.root):
        paths = [c.path for c in gitutil.changed(repo.base())]
    assert "src/kaleta/auth/helper.py" in paths
    assert "src/kaleta/util/helper.py" in paths
    approve(repo, cross_family_present=True)
    out = repo.gate()
    assert repo.state("mode") == "C", _reason(out)
