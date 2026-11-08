# SPDX-License-Identifier: AGPL-3.0-or-later
"""Diffs the gate must survive and ways around it that must stay closed (ultrareview)."""

from __future__ import annotations

import contextlib
import json

import gitutil
import protected
from conftest import HarnessRepo, approve, clean, fake_samples


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


def test_the_implementer_cannot_lower_k_below_the_profile(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    fake = fake_samples(repo, [clean()] * 3)
    for env in ({"KALETA_CRITIC_SAMPLES": "1"}, {}):
        args = ["scripts/review_gate.sh"] + (["--samples", "1"] if not env else [])
        out = repo.run(*args, env={"KALETA_CRITIC_FAKE": fake, **env})
        assert out.returncode == 0, out.stderr
        c = json.loads(repo.state("critic.json") or "{}")
        assert len(c["samples"]) == 3  # medium risk: critic_samples = 3


def test_the_gate_blocks_a_critic_run_with_too_few_samples(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    approve(repo, samples_ok=1)  # e.g. a critic.json from an older or hand-run critic
    reason = _reason(repo.gate())
    assert "1 sample" in reason
    assert repo.state("result") is None


def test_canned_critic_answers_outside_the_tests_are_a_veto(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    fake = fake_samples(repo, [clean()] * 3)
    assert repo.run("scripts/review_gate.sh", env={"KALETA_CRITIC_FAKE": fake}).returncode == 0
    assert json.loads(repo.state("critic.json") or "{}")["fake"] is True
    repo.gate(env={"KALETA_HARNESS_TEST": "0"})  # a real hook: not the test suite
    assert repo.state("result") == "escalated"
    assert "canned" in (repo.state("escalated-reason") or "")


def test_an_import_failure_in_the_judge_ends_the_run(repo: HarnessRepo) -> None:
    repo.new_plan()
    (repo.root / "scripts/harness/judge.py").write_text("this is not python(\n", encoding="utf-8")
    out = repo.gate()
    assert out.returncode == 0  # a hook error code is not a block in Claude Code
    assert out.stdout.strip() == ""
    assert repo.state("result") == "escalated"
    assert "could not run" in (repo.state("escalated-reason") or "")


def test_a_missing_gate_ends_the_run_instead_of_blocking(repo: HarnessRepo) -> None:
    repo.new_plan()
    (repo.root / "scripts/harness/gate.py").unlink()
    out = repo.gate()
    assert out.stdout.strip() == ""
    assert repo.state("result") == "escalated"


def test_the_law_on_main_wins_even_when_it_is_empty(repo: HarnessRepo) -> None:
    """An empty protected-paths list on main is the law; the diff's version is not."""
    repo.write("docs/harness/protected-paths.txt", "# nothing protected\n")
    repo.commit("owner empties the list on main")
    repo.new_plan()
    repo.write("docs/harness/protected-paths.txt", "src/*\n")
    repo.write("src/app.py", "X = 2\n")
    repo.commit("the diff writes its own list")
    with contextlib.chdir(repo.root):
        base = repo.base()
        assert (
            gitutil.read_at(repo.root, base, "docs/harness/protected-paths.txt")
            == "# nothing protected\n"
        )
        assert gitutil.read_at(repo.root, base, "docs/new-file.md") is None
    assert protected.load_rules(repo.root, base=base) == []


def test_read_at_falls_back_to_the_working_tree_only_for_files_new_in_the_diff(
    repo: HarnessRepo,
) -> None:
    repo.new_plan()
    repo.write("docs/brand-new.md", "new\n")
    base = repo.base()
    assert gitutil.read_at(repo.root, base, "docs/brand-new.md") == "new\n"
    assert gitutil.read_at(repo.root, None, "docs/brand-new.md") == "new\n"
