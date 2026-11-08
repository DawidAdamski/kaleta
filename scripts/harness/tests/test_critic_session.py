# SPDX-License-Identifier: AGPL-3.0-or-later
"""The critic's own claude -p sessions must not trigger the implementer's Stop hook."""

from __future__ import annotations

import json

import gate_log
from conftest import HarnessRepo, clean


def test_the_gate_ignores_a_critic_session(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    out = repo.gate(env={"KALETA_CRITIC_SESSION": "1"})
    assert out.stdout.strip() == ""
    assert repo.state("attempts") is None
    assert gate_log.records(repo.root, "fixture") == []


def test_critic_samples_run_marked_as_critic_sessions(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    bindir = repo.root.parent / "bin"
    bindir.mkdir(exist_ok=True)
    seen = repo.root.parent / "seen-env"
    payload = {"structured_output": clean(), "total_cost_usd": 0.01, "num_turns": 2}
    (bindir / "claude").write_text(
        "#!/usr/bin/env bash\n"
        f'echo "${{KALETA_CRITIC_SESSION:-unset}}" >> {seen}\n'
        f"echo '{json.dumps(payload)}'\n"
    )
    (bindir / "claude").chmod(0o755)
    out = repo.run("scripts/review_gate.sh", env={"PATH": f"{bindir}:/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    assert seen.read_text().split() == ["1", "1", "1"]
    assert repo.state("attempts") is None
