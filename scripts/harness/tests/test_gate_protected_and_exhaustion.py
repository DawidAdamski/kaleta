# SPDX-License-Identifier: AGPL-3.0-or-later
"""The gate vetoes protected paths changed through Bash, and exhaustion is terminal."""

from __future__ import annotations

import json

from conftest import HarnessRepo, approve


def _reason(out) -> str:
    return json.loads(out.stdout)["reason"] if out.stdout.strip() else ""


def test_bash_edit_of_a_protected_path_is_vetoed(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("scripts/harness/sneaky.py", "print('the judge is lenient')\n")
    repo.commit("edit the judge via bash")
    approve(repo)
    out = repo.gate()
    assert out.stdout.strip() == ""  # no more attempts: the owner decides
    assert repo.state("result") == "escalated"
    assert repo.state("mode") == "D"
    reason = repo.state("escalated-reason") or ""
    assert "Protected paths changed outside maintainer mode" in reason
    assert "scripts/harness/sneaky.py" in reason


def test_untracked_protected_file_is_vetoed_too(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("docs/harness/profile.toml", "[autonomy]\nallow_auto_merge = true\n")
    approve(repo)
    repo.gate()
    assert repo.state("result") == "escalated"
    assert "docs/harness/profile.toml" in (repo.state("escalated-reason") or "")


def test_maintainer_mode_clears_the_veto(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("scripts/harness/legit.py", "X = 1\n")
    repo.commit("maintainer change")
    approve(repo)
    out = repo.gate(env={"KALETA_HARNESS_MAINTAINER": "1"})
    assert "Protected paths" not in _reason(out)


def test_run_logs_written_by_the_harness_are_not_vetoed(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.write("docs/harness/runs/fixture.jsonl", "{}\n")
    repo.commit("work + log")
    approve(repo)
    assert "Protected paths" not in _reason(repo.gate())


def test_exhaustion_is_terminal_until_rearmed(repo: HarnessRepo) -> None:
    repo.new_plan(criteria=["- `test -f src/missing.py`"])
    repo.write(".claude/state/max-attempts", "1")
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    first = repo.gate()
    assert first.returncode == 0
    assert first.stdout.strip() == ""
    assert repo.state("result") == "exhausted"
    assert repo.state("attempts") == "1"

    # everything is fixed now — the gate must still not flip exhausted to done
    repo.write("src/missing.py", "\n")
    repo.commit("fix")
    approve(repo)
    again = repo.gate()
    assert again.returncode == 0
    assert repo.state("result") == "exhausted"
    assert repo.state("attempts") == "1"

    # re-arming starts over
    repo.run("scripts/plan_goal.sh", "start", "fixture", check=True)
    assert repo.state("result") is None
    assert repo.state("attempts") is None


def test_dry_run_still_reports_after_exhaustion(repo: HarnessRepo) -> None:
    repo.new_plan(criteria=["- `test -f src/missing.py`"])
    repo.write(".claude/state/result", "exhausted")
    out = repo.gate(env={"DOD_GATE_DRY": "1"})
    assert "Acceptance criterion failed" in _reason(out)
