# SPDX-License-Identifier: AGPL-3.0-or-later
"""protect-files.sh blocks the harness and the owner's rules; maintainer mode lets edits through."""

from __future__ import annotations

import pytest
from conftest import HarnessRepo, edit_payload
from protected import is_protected

CASES = [
    (".claude/hooks/dod-gate.sh", True),
    (".claude/settings.json", True),
    (".claude/state/review-verdict.json", True),
    (".claude/commands/implement-plan.md", True),
    ("scripts/verify.sh", True),
    ("scripts/review_gate.sh", True),
    ("scripts/harness/judge.py", True),
    ("docs/harness/profile.toml", True),
    ("docs/harness/runs/fixture.jsonl", True),
    ("docs/review-checklist.md", True),
    ("tests/harness/critic_cases/case-1/gold.json", True),
    ("docs/plans/archive/old.md", True),
    ("docs/plans/fixture.md", False),
    ("src/app.py", False),
    ("scripts/other.sh", False),
    ("alembic/versions/0002_new.py", False),
]


@pytest.mark.parametrize(("rel", "blocked"), CASES)
def test_edit_guard(repo: HarnessRepo, rel: str, blocked: bool) -> None:
    out = repo.run(".claude/hooks/protect-files.sh", stdin=edit_payload(str(repo.root / rel)))
    assert (out.returncode == 2) is blocked, out.stderr
    assert is_protected(rel, "edit", repo.root) is blocked


def test_tracked_migration_is_immutable_new_one_is_not(repo: HarnessRepo) -> None:
    repo.write("alembic/versions/0001_init.py", "x = 1\n")
    repo.commit("migration")
    old = repo.run(
        ".claude/hooks/protect-files.sh",
        stdin=edit_payload(str(repo.root / "alembic/versions/0001_init.py")),
    )
    new = repo.run(
        ".claude/hooks/protect-files.sh",
        stdin=edit_payload(str(repo.root / "alembic/versions/0002_next.py")),
    )
    assert old.returncode == 2
    assert "immutable" in old.stderr
    assert new.returncode == 0


def test_maintainer_mode_lets_the_edit_through_and_says_so(repo: HarnessRepo) -> None:
    out = repo.run(
        ".claude/hooks/protect-files.sh",
        stdin=edit_payload(str(repo.root / "scripts/harness/judge.py")),
        env={"KALETA_HARNESS_MAINTAINER": "1"},
    )
    assert out.returncode == 0
    assert "maintainer edit scripts/harness/judge.py" in out.stderr


def test_relative_path_and_non_edit_payloads(repo: HarnessRepo) -> None:
    rel = repo.run(
        ".claude/hooks/protect-files.sh", stdin=edit_payload("docs/harness/profile.toml")
    )
    assert rel.returncode == 2
    empty = repo.run(".claude/hooks/protect-files.sh", stdin='{"tool_input": {}}')
    assert empty.returncode == 0


def test_missing_matcher_refuses_everything(repo: HarnessRepo) -> None:
    (repo.root / "scripts/harness/protected-lib.sh").unlink()
    out = repo.run(
        ".claude/hooks/protect-files.sh", stdin=edit_payload(str(repo.root / "src/app.py"))
    )
    assert out.returncode == 2
    assert "missing" in out.stderr


def test_diff_mode_exempts_harness_written_logs(repo: HarnessRepo) -> None:
    base = repo.git("rev-parse", "HEAD")
    assert not is_protected("docs/harness/runs/x.jsonl", "diff", repo.root, base=base)
    assert is_protected("docs/harness/profile.toml", "diff", repo.root, base=base)
