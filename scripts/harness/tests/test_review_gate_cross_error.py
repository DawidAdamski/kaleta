# SPDX-License-Identifier: AGPL-3.0-or-later
"""A requested cross-family review that cannot run is an error, not a silent skip."""

from __future__ import annotations

import json
import os

from conftest import HarnessRepo

FAKE_CLAUDE = """#!/usr/bin/env bash
echo '{"structured_output": {"verdict": "approve", "findings": []}, "total_cost_usd": 0.01}'
"""


def _fake_bin(repo: HarnessRepo) -> str:
    bindir = repo.root.parent / "bin"
    bindir.mkdir(exist_ok=True)
    claude = bindir / "claude"
    claude.write_text(FAKE_CLAUDE, encoding="utf-8")
    claude.chmod(0o755)
    # only the fake claude plus the system tools — no Cursor CLI on PATH
    return f"{bindir}:/usr/bin:/bin"


def test_single_reviewer_still_approves(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    out = repo.run("scripts/review_gate.sh", env={"PATH": _fake_bin(repo)})
    assert out.returncode == 0, out.stderr
    assert json.loads(repo.state("review-verdict.json") or "{}")["verdict"] == "approve"


def test_missing_cursor_cli_is_an_error(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    assert "agent" not in os.listdir(repo.root.parent)
    out = repo.run(
        "scripts/review_gate.sh", env={"PATH": _fake_bin(repo), "KALETA_CROSS_REVIEW": "1"}
    )
    assert out.returncode != 0
    verdict = json.loads(repo.state("review-verdict.json") or "{}")
    assert verdict["verdict"] == "error"
    assert any("not installed" in f["summary"] for f in verdict["findings"])
