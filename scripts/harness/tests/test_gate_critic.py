# SPDX-License-Identifier: AGPL-3.0-or-later
"""The gate reads the critic's probabilities, never a verdict."""

from __future__ import annotations

import json

from conftest import HarnessRepo, answers, approve, fake_samples


def _reason(out) -> str:
    return json.loads(out.stdout)["reason"] if out.stdout.strip() else ""


def _work(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")


def _q(p: float, violations: int, k: int = 3) -> dict:
    return {
        "id": "Q-SCOPE",
        "p_violation": p,
        "violations": violations,
        "k_valid": k,
        "evidence": [{"file": "src/app.py", "line": 1}] if violations else [],
        "notes": ["touches an unrelated module"] if violations else [],
    }


def test_no_critic_run_blocks(repo: HarnessRepo) -> None:
    _work(repo)
    assert "No critic run yet" in _reason(repo.gate())


def test_stale_critic_blocks(repo: HarnessRepo) -> None:
    _work(repo)
    approve(repo)
    repo.write("src/app.py", "X = 3\n")
    assert "stale" in _reason(repo.gate())


def test_clean_critic_lets_the_plan_finish(repo: HarnessRepo) -> None:
    _work(repo)
    approve(repo)
    out = repo.gate()
    assert out.stdout.strip() == ""
    assert repo.state("result") == "done"


def test_a_majority_blocks_with_the_evidence(repo: HarnessRepo) -> None:
    _work(repo)
    approve(repo, [_q(0.6667, 2)])
    reason = _reason(repo.gate())
    assert "Critic found a problem: Q-SCOPE" in reason
    assert "src/app.py:1" in reason
    assert "touches an unrelated module" in reason


def test_a_single_sample_only_warns(repo: HarnessRepo) -> None:
    _work(repo)
    approve(repo, [_q(0.3333, 1)])
    out = repo.gate()
    assert out.stdout.strip() == ""  # done, with a warning on stderr
    assert "Critic is unsure: Q-SCOPE" in out.stderr


def test_critic_error_blocks(repo: HarnessRepo) -> None:
    _work(repo)
    approve(repo, status="error", error="cross-family sample required but failed")
    assert "Critic could not run: cross-family sample required" in _reason(repo.gate())


def test_end_to_end_with_fake_samples(repo: HarnessRepo) -> None:
    _work(repo)
    fake = fake_samples(
        repo,
        [answers(Q_SCOPE=("yes", "src/app.py", 1))] * 2 + [answers(Q_SCOPE="no")],
    )
    assert repo.run("scripts/review_gate.sh", env={"KALETA_CRITIC_FAKE": fake}).returncode == 0
    assert "Critic found a problem: Q-SCOPE" in _reason(repo.gate())
