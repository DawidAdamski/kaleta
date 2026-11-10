# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mutation operators and case building of ``seed_defects.py`` on a fixture repo.

Plan ``critic-calibration-set``: a throwaway git repo with one plan PR merged
into ``main`` the way GitHub merges it. Each operator must change exactly the
fact its question asks about; the builder must find the merge, label the case
clean, and give the mutated question a ``yes`` while the rest stay ``no``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import critic
import pytest
import seed_defects
from seed_defects import Tree

REPO = Path(__file__).resolve().parents[3]
PLAN = "foo-total"

BASE_FILES = {
    "src/kaleta/services/foo_service.py": (
        '"""Foo service."""\n\n\ndef old_total(xs):\n    return sum(xs)\n'
    ),
    "src/kaleta/views/foo.py": (
        '"""Foo page."""\n\nfrom kaleta.services import with_session\n\n\n'
        "async def page():\n    return None\n"
    ),
    "src/kaleta/models/foo.py": "class Foo:\n    pass\n",
    "src/kaleta/config/tidy.py": '"""Settings that nothing in this PR touches."""\n\nX = 1\n',
    "docs/bdd.md": "# BDD\n\n  KAL-FOO-001 @automated\n  Scenario: old\n    Given old\n",
    "tests/unit/test_old.py": '"""Covers: KAL-FOO-001"""\n\n\ndef test_old():\n    assert True\n',
}

PR_FILES = {
    "src/kaleta/services/foo_service.py": BASE_FILES["src/kaleta/services/foo_service.py"]
    + "\n\ndef compute_total(xs):\n    return round(sum(xs), 2)\n",
    "src/kaleta/views/foo.py": (
        '"""Foo page."""\n\nfrom kaleta.services import with_session\n\n\n'
        "async def page():\n    total = await with_session(_load)\n    return total\n"
    ),
    "src/kaleta/models/foo.py": "class Foo:\n    amount = 0\n",
    "alembic/versions/0002_foo_amount.py": (
        "def upgrade():\n    pass\n\n\ndef downgrade():\n    pass\n"
    ),
    "docs/bdd.md": BASE_FILES["docs/bdd.md"]
    + "\n  KAL-FOO-002 @automated\n  Scenario: total\n    Given numbers\n    Then a total\n",
    "tests/unit/test_foo_total.py": (
        '"""Covers: KAL-FOO-002"""\n\nfrom kaleta.services.foo_service import compute_total\n\n\n'
        "def test_total():\n    assert compute_total([1, 2]) == 3\n"
    ),
    # the scenario is covered by an e2e test as well, so deleting the unit test of
    # compute_total leaves KAL-FOO-002 covered (one fact changes, not two)
    "tests/e2e/test_foo_page.py": (
        '"""Covers: KAL-FOO-002"""\n\n\ndef test_page():\n    assert True\n'
    ),
    f"docs/plans/{PLAN}.md": (
        f"---\nplan_id: {PLAN}\n---\n\n# Foo total\n\n## Scope\n- add compute_total\n\n"
        "## Implementation notes\n\n- compute_total rounds to cents.\n"
    ),
}


def run(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    run("init", "-q", "-b", "main", cwd=root)
    run("config", "user.email", "t@example.com", cwd=root)
    run("config", "user.name", "T", cwd=root)
    run("config", "commit.gpgsign", "false", cwd=root)
    write(root, BASE_FILES)
    run("add", "-A", cwd=root)
    run("commit", "-q", "-m", "base", cwd=root)
    run("checkout", "-q", "-b", f"plan/{PLAN}", cwd=root)
    write(root, PR_FILES)
    run("add", "-A", cwd=root)
    run("commit", "-q", "-m", "feat: foo total", cwd=root)
    run("checkout", "-q", "main", cwd=root)
    run(
        "merge", "-q", "--no-ff", f"plan/{PLAN}", "-m",
        f"Merge pull request #7 from owner/plan/{PLAN}", cwd=root,
    )  # fmt: skip
    return root


@pytest.fixture
def merge(repo: Path) -> seed_defects.Merge:
    return seed_defects.find_merges(repo, [PLAN, "unrelated"])[PLAN]


@pytest.fixture
def tree(repo: Path, merge: seed_defects.Merge, tmp_path: Path) -> Tree:
    work = tmp_path / "work"
    run("worktree", "add", "-q", "--detach", str(work), merge.head, cwd=repo)
    return Tree.load(work, PLAN, merge.base)


def changed(tree: Tree) -> str:
    return run("status", "--porcelain", cwd=tree.root)


# ── history ──────────────────────────────────────────────────────────────
def test_find_merges_reads_the_pr_merge(repo: Path, merge: seed_defects.Merge) -> None:
    assert merge.pr == 7
    assert run("rev-parse", f"plan/{PLAN}", cwd=repo).strip() == merge.head
    assert run("rev-parse", "main~1", cwd=repo).strip() == merge.base


def test_the_archive_pr_is_not_the_work(repo: Path) -> None:
    run("checkout", "-q", "-b", f"docs/archive-{PLAN}", cwd=repo)
    (repo / "docs/plans/archive").mkdir(parents=True)
    run("mv", f"docs/plans/{PLAN}.md", "docs/plans/archive/", cwd=repo)
    run("commit", "-q", "-m", "archive", cwd=repo)
    run("checkout", "-q", "main", cwd=repo)
    run(
        "merge", "-q", "--no-ff", f"docs/archive-{PLAN}", "-m",
        f"Merge pull request #8 from owner/docs/archive-{PLAN}", cwd=repo,
    )  # fmt: skip
    assert seed_defects.find_merges(repo, [PLAN])[PLAN].pr == 7


def test_a_later_fix_on_the_same_source_makes_the_case_unclean(
    repo: Path, merge: seed_defects.Merge
) -> None:
    paths = seed_defects.changed_paths(repo, merge.base, merge.head)
    assert seed_defects.is_clean(repo, merge, paths)[0] is True
    (repo / "src/kaleta/services/foo_service.py").write_text("# fixed\n", encoding="utf-8")
    run("commit", "-q", "-am", "fix(foo): round half up", cwd=repo)
    clean, why = seed_defects.is_clean(repo, merge, paths)
    assert clean is False
    assert "fix(foo)" in why


# ── operators ────────────────────────────────────────────────────────────
def test_scope_edits_an_untouched_module_only(tree: Tree) -> None:
    mutation = seed_defects.op_scope(tree)
    assert mutation is not None and mutation.question == "Q-SCOPE"
    assert changed(tree).split() == ["M", "src/kaleta/config/tidy.py"]
    text = (tree.root / "src/kaleta/config/tidy.py").read_text(encoding="utf-8")
    assert "tidied while passing through" in text
    compile(text, "tidy.py", "exec")  # still Python


def test_service_test_removes_the_test_of_the_new_function(tree: Tree) -> None:
    mutation = seed_defects.op_service_test(tree)
    assert mutation is not None and mutation.question == "Q-SERVICE-TEST"
    assert "compute_total" in mutation.note
    assert not (tree.root / "tests/unit/test_foo_total.py").exists()
    assert (tree.root / "tests/unit/test_old.py").exists()


def test_service_test_keeps_a_test_that_names_a_scenario_nothing_else_covers(
    tree: Tree,
) -> None:
    """Deleting the only ``Covers: KAL-FOO-002`` would flip Q-KAL-SCENARIO too."""
    run("rm", "-q", "tests/e2e/test_foo_page.py", cwd=tree.root)
    run("commit", "-q", "-m", "only the unit test covers the scenario", cwd=tree.root)
    tree = Tree.load(tree.root, PLAN, tree.base)
    assert seed_defects.op_service_test(tree) is None
    assert (tree.root / "tests/unit/test_foo_total.py").exists()
    assert changed(tree) == ""


def test_view_logic_writes_a_query_into_the_changed_view(tree: Tree) -> None:
    mutation = seed_defects.op_view_logic(tree)
    assert mutation is not None and mutation.question == "Q-VIEW-LOGIC"
    text = (tree.root / "src/kaleta/views/foo.py").read_text(encoding="utf-8")
    assert "select(func.coalesce(func.sum(Transaction.amount)" in text
    compile(text, "foo.py", "exec")
    assert changed(tree).split() == ["M", "src/kaleta/views/foo.py"]


def test_tenant_swaps_one_new_family_session_for_the_registry(tree: Tree) -> None:
    mutation = seed_defects.op_tenant(tree)
    assert mutation is not None and mutation.question == "Q-TENANT-ISOLATION"
    text = (tree.root / "src/kaleta/views/foo.py").read_text(encoding="utf-8")
    assert "total = await with_public_session(_load)" in text
    assert "from kaleta.services.session import with_public_session" in text
    compile(text, "foo.py", "exec")


def test_kal_removes_the_new_scenario_and_its_covers(tree: Tree) -> None:
    mutation = seed_defects.op_kal(tree)
    assert mutation is not None and mutation.question == "Q-KAL-SCENARIO"
    bdd = (tree.root / "docs/bdd.md").read_text(encoding="utf-8")
    assert "KAL-FOO-002" not in bdd
    assert "KAL-FOO-001" in bdd  # the old scenario stays
    test = (tree.root / "tests/unit/test_foo_total.py").read_text(encoding="utf-8")
    assert "KAL-FOO-002" not in test
    assert "assert compute_total" in test  # the test itself stays


def test_strip_covers_keeps_other_ids_and_drops_an_empty_line() -> None:
    text = '"""Covers: KAL-A-001, KAL-A-002"""\n    Covers: KAL-A-002\nx = 1\n'
    assert seed_defects.strip_covers(text, "KAL-A-002") == '"""Covers: KAL-A-001"""\nx = 1\n'


def test_notes_claims_a_test_that_is_not_there(tree: Tree) -> None:
    mutation = seed_defects.op_notes(tree)
    assert mutation is not None and mutation.question == "Q-NOTES-TRUTH"
    plan = (tree.root / f"docs/plans/{PLAN}.md").read_text(encoding="utf-8")
    claimed = "tests/unit/test_foo_total_edge_cases.py"
    assert claimed in plan
    assert not (tree.root / claimed).exists()
    assert changed(tree).split() == ["M", f"docs/plans/{PLAN}.md"]


def test_migration_deletes_the_migration_of_the_model_change(tree: Tree) -> None:
    mutation = seed_defects.op_migration(tree)
    assert mutation is not None and mutation.question == "Q-MIGRATION"
    assert not (tree.root / "alembic/versions/0002_foo_amount.py").exists()
    assert (tree.root / "src/kaleta/models/foo.py").exists()


def test_an_operator_that_does_not_fit_changes_nothing(
    repo: Path, merge: seed_defects.Merge, tmp_path: Path
) -> None:
    work = tmp_path / "bare"
    run("worktree", "add", "-q", "--detach", str(work), merge.base, cwd=repo)
    tree = Tree.load(work, PLAN, merge.base)  # an empty diff: nothing to mutate
    for name, func in seed_defects.OPERATOR_FUNCS.items():
        if name == "M-SCOPE":
            continue  # needs only an untouched module, which every tree has
        assert func(tree) is None, name
    assert changed(tree) == ""


# ── building ─────────────────────────────────────────────────────────────
def test_build_gives_one_clean_case_and_one_mutant_per_operator(
    repo: Path, merge: seed_defects.Merge, tmp_path: Path
) -> None:
    questions = critic.load_questions(REPO)
    cases, reason = seed_defects.build_plan_cases(repo, merge, questions, tmp_path / "scratch")
    assert reason == ""
    by_id = {c.id: c for c in cases}
    assert by_id[PLAN].kind == "clean"
    assert set(by_id[PLAN].gold.values()) == {"no"}
    assert {c.operator for c in cases if c.kind == "mutant"} == set(seed_defects.OPERATORS)
    assert len({c.split for c in cases}) == 1
    for case in cases:
        if case.kind != "mutant":
            continue
        assert case.gold[case.target] == "yes", case.id
        assert [q for q, g in case.gold.items() if g == "yes"] == [case.target], case.id
        assert case.patch.startswith("diff --git"), case.id
    # the scratch worktree is gone again
    assert "scratch" not in run("worktree", "list", cwd=repo)


def test_written_cases_round_trip_and_pin_the_test_split(
    repo: Path, merge: seed_defects.Merge, tmp_path: Path
) -> None:
    questions = critic.load_questions(REPO)
    cases, _ = seed_defects.build_plan_cases(repo, merge, questions, tmp_path / "scratch")
    out = Path("tests/harness/critic_cases")
    seed_defects.write_cases(repo, cases, out)
    loaded = seed_defects.load_cases(repo, out)
    assert [c["id"] for c in loaded] == sorted(c.id for c in cases)
    mutant = next(c for c in cases if c.kind == "mutant")
    assert (repo / out / mutant.id / "mutation.patch").read_text(encoding="utf-8") == mutant.patch
    digest = seed_defects.write_test_pin(repo, out)
    assert (repo / seed_defects.TEST_SPLIT_PIN).read_text(encoding="utf-8").startswith(digest)


def test_a_pr_without_its_plan_file_is_skipped(
    repo: Path, merge: seed_defects.Merge, tmp_path: Path
) -> None:
    moved = seed_defects.Merge(
        PLAN + "-other", merge.pr, merge.merge, merge.base, merge.head, merge.merged_at
    )
    cases, reason = seed_defects.build_plan_cases(
        repo, moved, critic.load_questions(REPO), tmp_path / "scratch"
    )
    assert cases == []
    assert "docs/plans/<id>.md" in reason
