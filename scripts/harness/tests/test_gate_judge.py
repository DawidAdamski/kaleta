# SPDX-License-Identifier: AGPL-3.0-or-later
"""The gate asks the judge: modes per change, escalation, pooling, the law comes from main."""

from __future__ import annotations

import json

import gate_log
import judge
from conftest import HarnessRepo, approve, clean, fake_samples


def _reason(out) -> str:
    return json.loads(out.stdout)["reason"] if out.stdout.strip() else ""


def _critic(repo: HarnessRepo, *samples: dict, cross: dict | None = None) -> None:
    fake = fake_samples(repo, list(samples), cross=cross)
    out = repo.run("scripts/review_gate.sh", env={"KALETA_CRITIC_FAKE": fake})
    assert out.returncode == 0, out.stderr


def test_high_risk_change_ends_in_mode_c_with_a_note(repo: HarnessRepo) -> None:
    repo.new_plan(criteria=["- `test -f src/kaleta/auth/session.py`"])
    repo.write("src/kaleta/auth/session.py", "TTL = 30\n")
    repo.commit("auth change")
    # high risk: the profile requires one sample from another model family
    _critic(repo, clean(), clean(), cross=clean())
    out = repo.gate()
    assert out.stdout.strip() == ""
    assert repo.state("result") == "done"
    assert repo.state("mode") == "C"
    note = repo.state("decision.md") or ""
    assert "**Done — mode C**" in note
    assert "src/kaleta/auth/session.py" in note
    critic = json.loads(repo.state("critic.json") or "{}")
    assert critic["risk_class"] == "high"
    assert critic["cross_family_present"] is True


def test_high_risk_without_the_cross_family_sample_goes_to_the_owner(repo: HarnessRepo) -> None:
    repo.new_plan(criteria=["- `test -f src/kaleta/auth/session.py`"])
    repo.write("src/kaleta/auth/session.py", "TTL = 30\n")
    repo.commit("auth change")
    fake = fake_samples(repo, [clean(), clean()])  # no cross.json: the Cursor CLI is missing
    assert repo.run("scripts/review_gate.sh", env={"KALETA_CRITIC_FAKE": fake}).returncode == 1
    repo.gate()
    assert repo.state("result") == "escalated"
    assert "cross-family" in (repo.state("escalated-reason") or "")


def test_docs_only_change_is_capped_at_b_while_uncalibrated(repo: HarnessRepo) -> None:
    repo.new_plan(criteria=["- `test -f docs/guide.md`"])
    repo.write("docs/guide.md", "# Guide\n")
    repo.commit("docs")
    _critic(repo, clean(), clean(), clean())
    repo.gate()
    assert repo.state("mode") == "B"
    assert "Capped at B" in (repo.state("decision.md") or "")


def test_uncertainty_that_survives_a_round_is_escalated(repo: HarnessRepo) -> None:
    repo.new_plan()
    unsure = clean(Q_SCOPE=("yes", "src/app.py", 1))
    repo.write("src/app.py", "X = 2\n")
    repo.commit("round 1")
    _critic(repo, unsure, clean(), clean())
    assert "The critic is unsure" in _reason(repo.gate())

    repo.write("src/app.py", "X = 3  # clarified\n")
    repo.commit("round 2")
    _critic(repo, unsure, clean(), clean())
    out = repo.gate()
    assert out.stdout.strip() == ""
    assert repo.state("result") == "escalated"
    assert repo.state("mode") == "C"
    assert "stayed unsure" in (repo.state("escalated-reason") or "")


def test_rerunning_the_critic_pools_samples_instead_of_rerolling(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    bad = clean(Q_SCOPE=("yes", "src/app.py", 1))
    _critic(repo, bad, bad, clean())  # 2/3: a problem
    _critic(repo, clean(), clean(), clean())  # hoping for a lucky draw
    reason = _reason(repo.gate())
    assert "Q-SCOPE p=0.33 (2/6)" in reason
    assert repo.state("result") is None


def test_the_profile_comes_from_main_not_from_the_diff(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    tampered = (
        (repo.root / "docs/harness/profile.toml")
        .read_text()
        .replace("allow_auto_merge = false", "allow_auto_merge = true")
    )
    repo.write("docs/harness/profile.toml", tampered)
    repo.commit("work + a friendlier law")
    approve(repo)
    repo.gate()
    assert repo.state("result") == "escalated"
    (rec,) = [r for r in gate_log.records(repo.root, "fixture") if r["kind"] == "gate"]
    assert rec["profile_source"] == "base"
    assert rec["profile"]["autonomy"]["allow_auto_merge"] is False


def test_maintainer_session_reads_the_working_tree_profile(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    approve(repo)
    repo.gate(env={"KALETA_HARNESS_MAINTAINER": "1"})
    (rec,) = [r for r in gate_log.records(repo.root, "fixture") if r["kind"] == "gate"]
    assert rec["profile_source"] == "worktree"


def test_dry_run_reports_an_escalation_without_changing_state(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("scripts/harness/x.py", "X = 1\n")
    repo.commit("sneaky")
    approve(repo)
    out = repo.gate(env={"DOD_GATE_DRY": "1"})
    assert "Would ESCALATE" in _reason(out)
    assert repo.state("result") is None


def test_every_recorded_decision_replays(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    repo.gate()  # no critic yet: block
    _critic(repo, clean(), clean(), clean())
    repo.gate()  # done
    log = gate_log.log_path(repo.root, "fixture")
    checked, skipped, bad = judge.replay(log)
    assert (checked, skipped, bad) == (2, 0, [])
    out = repo.run(repo.env["KALETA_HARNESS_PY"], "scripts/harness/judge.py", "replay", str(log))
    assert out.returncode == 0, out.stderr
