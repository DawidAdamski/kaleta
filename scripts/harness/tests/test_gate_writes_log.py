# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every gate run and every review run leaves a record in docs/harness/runs/."""

from __future__ import annotations

import json

import gate_log
import pytest
from conftest import HarnessRepo, clean, fake_samples


def _records(repo: HarnessRepo, plan_id: str = "fixture") -> list[dict]:
    return gate_log.records(repo.root, plan_id)


def test_gate_run_is_recorded_with_its_evidence(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    repo.gate()
    (rec,) = [r for r in _records(repo) if r["kind"] == "gate"]
    assert rec["attempt"] == 1
    assert rec["dry"] is False
    assert rec["outcome"] == "block"  # no review yet
    assert rec["diff_hash"] == repo.diff_hash()
    names = [c["name"] for c in rec["inputs"]["checks"]]
    assert "criterion: test -f src/app.py" in names
    assert any(n.startswith("verify.sh") for n in names)
    assert {"path": "src/app.py", "added": 1, "removed": 1, "untracked": False} in rec["inputs"][
        "changed"
    ]
    assert gate_log.verify(repo.root) == []


def test_dry_run_is_marked_and_not_counted(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.run("scripts/plan_goal.sh", "check")
    (rec,) = _records(repo)
    assert rec["dry"] is True
    assert repo.state("attempts") is None


def test_review_is_recorded_and_log_lines_do_not_stale_it(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    fake = fake_samples(repo, [clean()] * 3)
    out = repo.run("scripts/review_gate.sh", env={"KALETA_CRITIC_FAKE": fake})
    assert out.returncode == 0, out.stderr
    reviews = [r for r in _records(repo) if r["kind"] == "review"]
    assert len(reviews) == 1
    assert reviews[0]["status"] == "ok"
    assert reviews[0]["cost_usd"] == pytest.approx(0.3)

    # the review log line is a change in docs/harness/runs/, yet the critic run stays fresh
    gate = repo.gate()
    reason = json.loads(gate.stdout)["reason"] if gate.stdout.strip() else ""
    assert "stale" not in reason
    assert repo.state("result") == "done"


def test_failed_critic_is_recorded_as_error(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    out = repo.run("scripts/review_gate.sh", env={"PATH": "/usr/bin:/bin"})  # no claude CLI
    assert out.returncode != 0
    (rec,) = [r for r in _records(repo) if r["kind"] == "review"]
    assert rec["status"] == "error"
    assert rec["error_kind"] == "no_samples"
