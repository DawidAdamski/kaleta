# SPDX-License-Identifier: AGPL-3.0-or-later
"""``critic.py --base``: the change's base given explicitly (plan critic-calibration-set).

The calibration runner replays old cases whose base is not ``main``'s
merge-base. Without the option the critic reviews the diff against the
merge-base, as the gate needs.
"""

from __future__ import annotations

import json
import sys

from conftest import HarnessRepo, answers, fake_samples

CRITIC = "scripts/harness/critic.py"


def _work(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\nY = 3\n")
    repo.commit("first")
    repo.write("src/other.py", "Z = 1\n")
    repo.commit("second")


def test_base_replaces_the_merge_base(repo: HarnessRepo) -> None:
    _work(repo)
    first = repo.git("rev-parse", "HEAD~1")
    fake = fake_samples(repo, [answers(Q_SCOPE="no")] * 3)
    out = repo.run(
        sys.executable, CRITIC, "fixture", "--base", first, env={"KALETA_CRITIC_FAKE": fake}
    )
    assert out.returncode == 0, out.stderr
    record = json.loads(repo.state("critic.json") or "{}")
    assert record["base"] == first
    assert record["diff_hash"] != repo.diff_hash()  # repo.diff_hash() is against the merge-base


def test_without_base_the_merge_base_is_used(repo: HarnessRepo) -> None:
    _work(repo)
    fake = fake_samples(repo, [answers(Q_SCOPE="no")] * 3)
    out = repo.run(sys.executable, CRITIC, "fixture", env={"KALETA_CRITIC_FAKE": fake})
    assert out.returncode == 0, out.stderr
    assert json.loads(repo.state("critic.json") or "{}")["base"] == repo.base()


def test_a_base_with_no_diff_has_nothing_to_review(repo: HarnessRepo) -> None:
    _work(repo)
    out = repo.run(sys.executable, CRITIC, "fixture", "--base", "HEAD")
    assert out.returncode == 1
    assert "nothing to review" in out.stderr
