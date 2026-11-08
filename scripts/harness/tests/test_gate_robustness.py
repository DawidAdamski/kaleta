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


def test_untracked_file_content_is_judged_secret(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    repo.write("src/settings_local.py", 'AWS_KEY = "AKIAABCDEFGHIJKLMNOP"\n')  # never git-added
    approve(repo)
    repo.gate()
    assert repo.state("result") == "escalated"
    assert "src/settings_local.py" in (repo.state("escalated-reason") or "")


def test_untracked_file_content_is_judged_green_washing(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("tests/test_new.py", "import pytest\n\n@pytest.mark.skip\ndef test_x():\n    pass\n")
    approve(repo)
    assert "New skip/xfail" in _reason(repo.gate())


def test_editing_an_untracked_file_makes_the_critic_stale(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/new_module.py", "X = 1\n")
    approve(repo)
    repo.write("src/new_module.py", "X = 2  # changed after the review\n")
    assert "stale" in _reason(repo.gate())


def test_deleting_a_whole_test_file_is_flagged(repo: HarnessRepo) -> None:
    repo.write("tests/test_money.py", "def test_sum():\n    assert 1 + 1 == 2\n")
    repo.commit("a test on main")
    repo.new_plan()
    repo.git("rm", "-q", "tests/test_money.py")
    repo.commit("drop the test")
    approve(repo)
    repo.gate()
    note = repo.state("decision.md") or ""
    assert "Assertions were removed" in note
    assert "tests/test_money.py" in note


BROKEN_PLANFILE = """
def section(text, heading):
    return ""


def plan_meta(text):
    raise RuntimeError("boom in the harness")
"""


def test_a_crashing_gate_ends_the_run_instead_of_blocking_forever(repo: HarnessRepo) -> None:
    repo.new_plan()
    (repo.root / "scripts/harness/planfile.py").write_text(BROKEN_PLANFILE, encoding="utf-8")
    first = repo.gate()
    assert first.stdout.strip() == ""  # not a block: the session may stop
    assert repo.state("result") == "escalated"
    assert repo.state("mode") == "D"
    assert "boom in the harness" in (repo.state("escalated-reason") or "")
    again = repo.gate()
    assert again.stdout.strip() == ""


def test_a_crash_in_a_dry_run_is_reported_not_recorded(repo: HarnessRepo) -> None:
    repo.new_plan()
    (repo.root / "scripts/harness/planfile.py").write_text(BROKEN_PLANFILE, encoding="utf-8")
    out = repo.gate(env={"DOD_GATE_DRY": "1"})
    assert "crashed" in _reason(out)
    assert repo.state("result") is None


def test_a_broken_run_log_is_a_veto_not_a_crash(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    repo.gate()  # one valid record
    log = repo.root / "docs/harness/runs/fixture.jsonl"
    log.write_text(log.read_text() + "not json at all\n")
    approve(repo)
    repo.gate()
    assert repo.state("result") == "escalated"
    reason = repo.state("escalated-reason") or ""
    assert "run log" in reason
    assert "crashed" not in reason
