# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures for the harness tests: a throwaway git repo with the real harness in it.

These tests live under ``scripts/harness/`` (protected, so the implementer
cannot edit the tests that hold the judge to account) and run without the
application, the database or a model: ``uv run pytest scripts/harness/tests``.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
HARNESS_DIR = REPO / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

import gitutil  # noqa: E402

COPY = [
    ".claude/hooks",
    ".claude/settings.json",
    ".claude/commands/implement-plan.md",
    "scripts/harness",
    "scripts/review_gate.sh",
    "scripts/plan_goal.sh",
    "scripts/plan_runner.sh",
    "docs/harness",
    "docs/review-checklist.md",
]

VERIFY_STUB = """#!/usr/bin/env bash
# test stub: fails when .verify-fail exists
[ -f .verify-fail ] && { echo "VERIFY FAILED (stub)"; exit 1; }
echo "VERIFY OK (stub)"
"""

PLAN = """---
plan_id: {id}
title: Fixture plan {id}
area: test
effort: small
status: {status}
{extra}---

# Fixture plan

## Intent
Test fixture.

## Scope
Covers: `src/app.py`.

## Acceptance criteria

{criteria}

## Touchpoints
- `src/app.py`

## Open questions
None.

## Implementation notes
{notes}
"""


@dataclass
class HarnessRepo:
    root: Path
    env: dict[str, str]

    def run(
        self, *cmd: str, stdin: str = "{}", env: dict[str, str] | None = None, check: bool = False
    ) -> subprocess.CompletedProcess[str]:
        full = {**self.env, **(env or {})}
        return subprocess.run(
            list(cmd),
            cwd=self.root,
            input=stdin,
            capture_output=True,
            text=True,
            env=full,
            check=check,
        )

    def git(self, *args: str) -> str:
        return self.run("git", *args, check=True).stdout.strip()

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self, msg: str = "change") -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", msg, "--allow-empty")

    def state(self, name: str) -> str | None:
        path = self.root / ".claude" / "state" / name
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def base(self) -> str:
        return self.git("merge-base", "HEAD", "main")

    def diff_hash(self) -> str:
        """The gate's own diff hash (one definition: gitutil.diff_hash)."""
        with contextlib.chdir(self.root):
            return gitutil.diff_hash(self.base())

    def new_plan(
        self,
        plan_id: str = "fixture",
        criteria: list[str] | None = None,
        notes: str = "Done: the fixture change.",
        extra: str = "",
    ) -> None:
        """Commit a draft plan on main, branch plan/<id>, arm the gate."""
        crit = criteria if criteria is not None else ["- `test -f src/app.py`"]
        self.git("checkout", "-q", "main")
        self.write(
            f"docs/plans/{plan_id}.md",
            PLAN.format(
                id=plan_id, status="draft", extra=extra, criteria="\n".join(crit), notes=notes
            ),
        )
        self.commit(f"plan {plan_id}")
        out = self.run("scripts/plan_goal.sh", "start", plan_id, check=False)
        assert out.returncode == 0, out.stderr

    def gate(self, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self.run(".claude/hooks/dod-gate.sh", env=env)


def _copy(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def make_repo(tmp_path: Path, base_env: dict[str, str]) -> HarnessRepo:
    """A throwaway repo with the real harness in it, isolated from the caller's git config."""
    root = tmp_path / "repo"
    root.mkdir()
    for rel in COPY:
        _copy(REPO / rel, root / rel)
    verify = root / "scripts" / "verify.sh"
    verify.write_text(VERIFY_STUB, encoding="utf-8")
    verify.chmod(0o755)
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("X = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        ".claude/state/\nlogs/\n.verify-fail\n__pycache__/\n", encoding="utf-8"
    )
    env = {
        k: v
        for k, v in base_env.items()
        if not k.startswith(("KALETA_", "CLAUDE", "GIT_", "DOD_GATE"))
    }
    # Ignore the developer's ~/.gitconfig and /etc/gitconfig (gpgsign, hooksPath,
    # defaultBranch …): verify.sh runs these tests for every plan.
    empty_config = tmp_path / "gitconfig"
    empty_config.write_text("", encoding="utf-8")
    env.update(
        GIT_CONFIG_GLOBAL=str(empty_config),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.invalid",
        KALETA_HARNESS_PY=sys.executable,
    )
    h = HarnessRepo(root, env)
    h.run("git", "init", "-q", "-b", "main", check=True)
    h.commit("base")
    return h


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[HarnessRepo]:
    yield make_repo(tmp_path, dict(os.environ))


def approve(repo: HarnessRepo, questions: list[dict] | None = None, **extra: object) -> None:
    """A fresh critic result for the current diff; by default every question is clean."""
    qs = (
        questions
        if questions is not None
        else [
            {
                "id": "Q-SCOPE",
                "p_violation": 0.0,
                "violations": 0,
                "k_valid": 3,
                "evidence": [],
                "notes": [],
            }
        ]
    )
    repo.write(
        ".claude/state/critic.json",
        json.dumps(
            {
                "version": 2,
                "diff_hash": repo.diff_hash(),
                "status": "ok",
                "critic_hash": "test",
                "samples_ok": 3,
                "cross_family_present": False,
                "questions": qs,
            }
            | extra
        ),
    )


def fake_samples(repo: HarnessRepo, samples: list[dict], cross: dict | None = None) -> str:
    """Write canned critic samples; returns the directory for KALETA_CRITIC_FAKE."""
    d = repo.root.parent / "fake-critic"
    d.mkdir(exist_ok=True)
    for f in d.glob("*.json"):
        f.unlink()
    for i, sample in enumerate(samples, start=1):
        (d / f"sample-{i}.json").write_text(json.dumps(sample), encoding="utf-8")
    if cross is not None:
        (d / "cross.json").write_text(json.dumps(cross), encoding="utf-8")
    return str(d)


def answers(**by_id: str | tuple[str, str, int]) -> dict:
    """answers(Q_SCOPE="no", Q_SERVICE_TEST=("yes", "src/app.py", 1)) -> a sample payload."""
    out = []
    for key, val in by_id.items():
        qid = key.replace("_", "-")
        if isinstance(val, tuple):
            out.append(
                {"id": qid, "answer": val[0], "evidence": [{"file": val[1], "line": val[2]}]}
            )
        else:
            out.append({"id": qid, "answer": val})
    return {"answers": out, "cost_usd": 0.1}


def clean(**overrides: str | tuple[str, str, int]) -> dict:
    """A sample that answers every question in the repo's set: "no", unless overridden."""
    import tomllib

    data = tomllib.loads((REPO / "docs/harness/critic-questions.toml").read_text(encoding="utf-8"))
    base: dict[str, str | tuple[str, str, int]] = {
        q["id"].replace("-", "_"): "no" for q in data["question"]
    }
    return answers(**(base | overrides))


def edit_payload(path: str) -> str:
    return json.dumps({"tool_name": "Edit", "tool_input": {"file_path": path}})
