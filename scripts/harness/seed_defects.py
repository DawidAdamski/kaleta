#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the critic's calibration cases from the repo's own history (plan critic-calibration-set).

    seed_defects.py [--max-plans N] [--plan ID ...] [--dry-run] [--out DIR]

**Clean cases.** For an archived plan whose PR merge commit on ``main`` is
known (``Merge pull request #N from <owner>/<…plan_id>``), the case is
``(base, head)``: ``base`` is the merge-base of the PR, ``head`` its last
commit, so ``git diff base head`` is exactly what the PR changed, plan file
included. A case is labelled clean only if no ``fix…`` commit touched the
same files within 30 days after the merge. That is a heuristic, and the
report says so.

**Seeded defects.** One mutation operator per question, applied to a clean
case so that exactly one fact changes (a counterfactual pair). The mutated
question's gold answer is ``yes``; every other applicable question copies
the clean case (``no``).

Cases are written as small bundles under ``tests/harness/critic_cases/``:
``case.json`` (refs into history, gold labels, split) and, for a mutant,
``mutation.patch`` to apply on top of ``head``. The directory is protected:
the implementer must not edit the exam.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import calibration  # noqa: E402
import critic  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CASES = Path("tests/harness/critic_cases")
TEST_SPLIT_PIN = Path("docs/harness/calibration/test-split.sha256")
ARCHIVE = Path("docs/plans/archive")
CLEAN_WINDOW_DAYS = 30
MERGE_RE = re.compile(r"^Merge pull request #(\d+) from [^/]+/(.+)$")

#: Files the calibration runner replaces with today's version before it runs
#: the critic on an old case (the questions, the profile, the hooks the critic
#: session loads). A case whose own diff touches one of them cannot be
#: replayed against today's critic and is skipped.
OVERLAY = (
    "docs/harness/critic-questions.toml",
    "docs/harness/profile.toml",
    "docs/review-checklist.md",
    ".claude/settings.json",
    ".claude/hooks/*",
)

#: Operator -> the question it seeds a violation for.
OPERATORS = {
    "M-SCOPE": "Q-SCOPE",
    "M-SERVICE-TEST": "Q-SERVICE-TEST",
    "M-VIEW-LOGIC": "Q-VIEW-LOGIC",
    "M-TENANT": "Q-TENANT-ISOLATION",
    "M-KAL": "Q-KAL-SCENARIO",
    "M-NOTES": "Q-NOTES-TRUTH",
    "M-MIGRATION": "Q-MIGRATION",
}


def git(*args: str, cwd: Path, check: bool = True) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace", check=False
    )
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


# ── history ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Merge:
    plan_id: str
    pr: int
    merge: str
    base: str
    head: str
    merged_at: str  # ISO date-time of the merge commit


def find_merges(repo: Path, plan_ids: list[str]) -> dict[str, Merge]:
    """The PR merge on ``main``'s first-parent line for each plan id that has one."""
    wanted = set(plan_ids)
    found: dict[str, Merge] = {}
    log = git("log", "--first-parent", "--merges", "--format=%H%x09%cI%x09%s", "main", cwd=repo)
    for line in log.splitlines():
        sha, when, subject = line.split("\t", 2)
        m = MERGE_RE.match(subject)
        if not m:
            continue
        branch = m.group(2)
        if branch.startswith("docs/archive"):
            continue  # the archive PR that follows a merge, not the work
        plan_id = next((p for p in wanted if branch == p or branch.endswith("/" + p)), None)
        if plan_id is None or plan_id in found:  # newest merge wins
            continue
        parents = git("rev-list", "--parents", "-n", "1", sha, cwd=repo).split()
        if len(parents) != 3:
            continue
        head = parents[2]
        base = git("merge-base", parents[1], head, cwd=repo).strip()
        found[plan_id] = Merge(plan_id, int(m.group(1)), sha, base, head, when)
    return found


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    return sorted(
        p
        for p in git("diff", "--no-renames", "--name-only", base, head, cwd=repo).splitlines()
        if p
    )


def is_clean(repo: Path, merge: Merge, paths: list[str]) -> tuple[bool, str]:
    """No ``fix`` commit touched the PR's source files within the window after the merge."""
    # Only the PR's Python sources: shared files (docs/bdd.md, the locale JSON,
    # chores.md) are touched by nearly every later fix and say nothing about this PR.
    src = [p for p in paths if p.startswith("src/") and p.endswith(".py")]
    if not src:
        return True, "no Python source changed"
    start = datetime.datetime.fromisoformat(merge.merged_at)
    end = start + datetime.timedelta(days=CLEAN_WINDOW_DAYS)
    log = git(
        "log", "main", "--no-merges", "--format=%h %s",
        f"--since={start.isoformat()}", f"--until={end.isoformat()}", "--", *src,
        cwd=repo,
    )  # fmt: skip
    fixes = [line for line in log.splitlines() if re.match(r"^\w+ fix(\(|:|!)", line)]
    if fixes:
        return False, f"fix within {CLEAN_WINDOW_DAYS} days: {fixes[0]}"
    return True, f"no fix commit on these files within {CLEAN_WINDOW_DAYS} days"


def touches_overlay(paths: list[str]) -> bool:
    return any(fnmatchcase(p, g) for p in paths for g in OVERLAY)


def gold_for(
    paths: list[str], questions: list[critic.Question], target: str = ""
) -> dict[str, str]:
    """``yes`` for the mutated question, ``no`` for every other applicable one."""
    return {q.id: ("yes" if q.id == target else "no") for q in critic.applicable(questions, paths)}


# ── the tree a mutation edits ────────────────────────────────────────────
@dataclass
class Tree:
    """A worktree at the case's ``head``, plus what the PR changed."""

    root: Path
    plan_id: str
    base: str
    paths: list[str]
    status: dict[str, str] = field(default_factory=dict)  # path -> A | M | D
    added: dict[str, list[str]] = field(default_factory=dict)  # path -> added lines

    @classmethod
    def load(cls, root: Path, plan_id: str, base: str) -> Tree:
        status: dict[str, str] = {}
        for line in git(
            "diff", "--no-renames", "--name-status", base, "HEAD", cwd=root
        ).splitlines():
            code, _, path = line.partition("\t")
            status[path] = code[:1]
        added: dict[str, list[str]] = {}
        path = ""
        for raw in git("diff", "--no-renames", "-U0", base, "HEAD", cwd=root).splitlines():
            if raw.startswith("+++ "):
                path = raw[6:] if raw.startswith("+++ b/") else ""
            elif raw.startswith("+") and path:
                added.setdefault(path, []).append(raw[1:])
        return cls(root, plan_id, base, sorted(status), status, added)

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).write_text(text, encoding="utf-8")

    def at_base(self, rel: str) -> str | None:
        out = subprocess.run(
            ["git", "show", f"{self.base}:{rel}"], cwd=self.root, capture_output=True, text=True,
            errors="replace", check=False,
        )  # fmt: skip
        return out.stdout if out.returncode == 0 else None

    def tracked(self) -> list[str]:
        return git("ls-files", cwd=self.root).splitlines()

    def grep_tests(self, needle: str) -> list[str]:
        out = git("grep", "-l", "-F", needle, "--", "tests", cwd=self.root, check=False)
        return [p for p in out.splitlines() if p]

    @property
    def plan_path(self) -> str:
        return f"docs/plans/{self.plan_id}.md"


@dataclass(frozen=True)
class Mutation:
    operator: str
    question: str
    note: str


Operator = Callable[[Tree], Mutation | None]


def _sorted_by_plan(items: list[str], plan_id: str) -> list[str]:
    """A stable, plan-dependent order, so different plans pick different files."""
    return sorted(items, key=lambda s: hashlib.sha256(f"{plan_id}:{s}".encode()).hexdigest())


# ── operators ────────────────────────────────────────────────────────────
#: Folders an M-SCOPE edit must stay out of: a change there would make another
#: question applicable with a "yes" of its own.
_SCOPE_AVOID = (
    "src/kaleta/services/", "src/kaleta/views/", "src/kaleta/api/", "src/kaleta/models/",
    "src/kaleta/auth/", "src/kaleta/db/", "src/kaleta/crypto/", "src/kaleta/main.py",
)  # fmt: skip


def op_scope(tree: Tree) -> Mutation | None:
    """A drive-by edit to a module the plan never mentions: its docstring grows a paragraph."""
    plan_text = tree.read(tree.plan_path) if (tree.root / tree.plan_path).exists() else ""
    dirs = {str(Path(p).parent) for p in tree.paths}
    candidates = [
        p
        for p in tree.tracked()
        if p.startswith("src/kaleta/")
        and p.endswith(".py")
        and not p.endswith("__init__.py")
        and not p.startswith(_SCOPE_AVOID)
        and p not in tree.status
        and str(Path(p).parent) not in dirs
        and Path(p).stem not in plan_text
    ]
    for rel in _sorted_by_plan(candidates, tree.plan_id):
        lines = tree.read(rel).splitlines(keepends=True)
        start = next(
            (i for i, line in enumerate(lines[:6]) if line.lstrip().startswith('"""')), None
        )
        if start is None:
            continue
        end = (
            start
            if lines[start].count('"""') >= 2
            else next((i for i in range(start + 1, len(lines)) if '"""' in lines[i]), None)
        )
        if end is None:
            continue
        if end == start:  # one-line docstring: """Text."""
            text = lines[start].rstrip("\n").rstrip()[:-3]
            lines[start] = (
                f"{text}\n\nThe helpers below were tidied while passing through: names now\n"
                "follow the module they live in, and the order matches the call order.\n"
                '"""\n'
            )
        else:
            lines.insert(
                end,
                "\nThe helpers below were tidied while passing through: names now\n"
                "follow the module they live in, and the order matches the call order.\n",
            )
        tree.write(rel, "".join(lines))
        return Mutation("M-SCOPE", OPERATORS["M-SCOPE"], f"docstring of {rel} rewritten")
    return None


_DEF = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")
_COVERS_ID = re.compile(r"KAL-[A-Z]+-\d+")


def op_service_test(tree: Tree) -> Mutation | None:
    """Delete the tests that cover a new service function (and only those)."""
    for rel in sorted(
        p for p in tree.added if p.startswith("src/kaleta/services/") and p.endswith(".py")
    ):
        before = tree.at_base(rel) or ""
        names = [
            m.group(1)
            for line in tree.added[rel]
            if (m := _DEF.match(line)) and f"def {m.group(1)}(" not in before
        ]
        for name in [n for n in names if not n.startswith("__")]:
            users = tree.grep_tests(name)
            if not users or any(tree.status.get(u) not in ("A", "M") for u in users):
                continue  # untested, or covered by a test the PR did not write
            kal_ids = {i for u in users for i in _COVERS_ID.findall(tree.read(u))}
            for u in users:
                old = tree.at_base(u) if tree.status[u] == "M" else None
                if old is None:
                    (tree.root / u).unlink()
                else:
                    tree.write(u, old)
            if tree.grep_tests(name):
                return None
            orphaned = [i for i in kal_ids if not tree.grep_tests(i)]
            if orphaned:  # would also flip Q-KAL-SCENARIO: not a one-fact change
                git("checkout", "HEAD", "--", *users, cwd=tree.root)
                continue
            return Mutation(
                "M-SERVICE-TEST",
                OPERATORS["M-SERVICE-TEST"],
                f"tests of {rel}:{name} removed ({', '.join(users)})",
            )
    return None


_VIEW_TEMPLATE = '''

async def _period_spend_total(session: "AsyncSession", account_id: int) -> "Decimal":
    """Outflows of the current month for this page's header."""
    import datetime
    from decimal import Decimal

    from sqlalchemy import func, select

    from kaleta.models.transaction import Transaction

    today = datetime.date.today()
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.account_id == account_id,
        Transaction.amount < 0,
        Transaction.date >= today.replace(day=1),
    )
    total = await session.scalar(stmt)
    return Decimal(total or 0).quantize(Decimal("0.01"))
'''


def op_view_logic(tree: Tree) -> Mutation | None:
    """A query and money arithmetic written inside a view the plan changed."""
    if not any(p.startswith("src/kaleta/services/") for p in tree.paths):
        return None
    views = sorted(
        p for p in tree.paths
        if p.startswith("src/kaleta/views/") and p.endswith(".py") and tree.status[p] in ("A", "M")
    )  # fmt: skip
    for rel in views:
        lines = tree.read(rel).splitlines(keepends=True)
        at = next(
            (i for i, line in enumerate(lines) if re.match(r"^(async def |def |class |@)", line)),
            None,
        )
        if at is None:
            continue
        lines.insert(at, _VIEW_TEMPLATE.lstrip("\n") + "\n\n")
        tree.write(rel, "".join(lines))
        return Mutation("M-VIEW-LOGIC", OPERATORS["M-VIEW-LOGIC"], f"query inlined into {rel}")
    return None


#: (family call, registry call, import the swap needs or "")
_TENANT_SWAPS = (
    (
        "with_session(",
        "with_public_session(",
        "from kaleta.services.session import with_public_session\n",
    ),
    ("AsyncSessionFactory()", "AsyncSessionFactory.public()", ""),
)


def op_tenant(tree: Tree) -> Mutation | None:
    """One new family-session call made on the public registry's session instead."""
    for rel in sorted(p for p in tree.added if p.startswith("src/") and p.endswith(".py")):
        text = tree.read(rel)
        for family, public, needs in _TENANT_SWAPS:
            new = [
                line
                for line in tree.added[rel]
                if family in line and "def " not in line and "import" not in line
            ]
            if not new or new[0] not in text:
                continue
            text = text.replace(new[0], new[0].replace(family, public, 1), 1)
            if needs:
                lines = text.splitlines(keepends=True)
                at = next((i for i, ln in enumerate(lines) if ln.startswith("from kaleta")), None)
                if at is None:
                    continue
                lines.insert(at, needs)
                text = "".join(lines)
            tree.write(rel, text)
            return Mutation("M-TENANT", OPERATORS["M-TENANT"], f"{family} -> {public} in {rel}")
    return None


_KAL_HEAD = re.compile(r"^\s*(KAL-[A-Z]+-\d+)\s+@")


def strip_covers(text: str, kal: str) -> str:
    """Remove *kal* from every ``Covers:`` line; a line left naming nothing goes."""
    out = []
    for line in text.splitlines(keepends=True):
        if kal in line and "Covers:" in line:
            line = re.sub(rf"\s*,?\s*{re.escape(kal)}\b,?", "", line)
            if not _COVERS_ID.search(line.split("Covers:", 1)[1]):
                line = re.sub(r"Covers:\s*", "", line)
                if not line.strip():
                    continue
        out.append(line)
    return "".join(out)


def op_kal(tree: Tree) -> Mutation | None:
    """The new KAL- scenario and every ``Covers:`` mention of it, removed."""
    bdd = "docs/bdd.md"
    if bdd not in tree.added:
        return None
    before = tree.at_base(bdd) or ""
    new_ids = [
        m.group(1)
        for line in tree.added[bdd]
        if (m := _KAL_HEAD.match(line)) and m.group(1) not in before
    ]
    if not new_ids:
        return None
    kal = new_ids[0]
    lines = tree.read(bdd).splitlines(keepends=True)
    start = next(
        i for i, line in enumerate(lines) if (m := _KAL_HEAD.match(line)) and m.group(1) == kal
    )
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if _KAL_HEAD.match(lines[i]) or lines[i].startswith("#")
        ),
        len(lines),
    )
    tree.write(bdd, "".join(lines[:start] + lines[end:]))
    for rel in tree.grep_tests(kal):
        tree.write(rel, strip_covers(tree.read(rel), kal))
    return Mutation("M-KAL", OPERATORS["M-KAL"], f"{kal} removed from docs/bdd.md and Covers:")


def op_notes(tree: Tree) -> Mutation | None:
    """Implementation notes claim a test that the diff does not contain."""
    rel = tree.plan_path
    if not (tree.root / rel).exists():
        return None
    text = tree.read(rel)
    m = re.search(r"^## Implementation notes[^\n]*\n", text, re.M)
    if not m:
        return None
    test = f"tests/unit/test_{tree.plan_id.replace('-', '_')}_edge_cases.py"
    if (tree.root / test).exists():
        return None
    claim = (
        f"\n- Edge cases are pinned by `{test}`: an empty input and a repeated one\n"
        "  each have their own test, so a regression there fails the suite.\n"
    )
    tree.write(rel, text[: m.end()] + claim + text[m.end() :])
    return Mutation("M-NOTES", OPERATORS["M-NOTES"], f"notes claim {test}")


def op_migration(tree: Tree) -> Mutation | None:
    """The migration that goes with a model change, deleted."""
    if not any(p.startswith("src/kaleta/models/") for p in tree.paths):
        return None
    migrations = [
        p for p in tree.paths
        if tree.status[p] == "A" and re.match(r"^alembic(_public)?/versions/.+\.py$", p)
    ]  # fmt: skip
    if not migrations:
        return None
    for rel in migrations:
        (tree.root / rel).unlink()
    return Mutation(
        "M-MIGRATION", OPERATORS["M-MIGRATION"], f"migration removed: {', '.join(migrations)}"
    )


OPERATOR_FUNCS: dict[str, Operator] = {
    "M-SCOPE": op_scope,
    "M-SERVICE-TEST": op_service_test,
    "M-VIEW-LOGIC": op_view_logic,
    "M-TENANT": op_tenant,
    "M-KAL": op_kal,
    "M-NOTES": op_notes,
    "M-MIGRATION": op_migration,
}


def capture_patch(root: Path) -> tuple[str, list[str]]:
    """The worktree's changes against HEAD as a binary patch, and the paths it touches."""
    git("add", "-A", cwd=root)
    patch = git("diff", "--cached", "--binary", "--no-renames", "HEAD", cwd=root)
    paths = [p for p in git("diff", "--cached", "--name-only", "HEAD", cwd=root).splitlines() if p]
    git("reset", "-q", "--hard", "HEAD", cwd=root)
    git("clean", "-q", "-fd", cwd=root)
    return patch, paths


# ── building ─────────────────────────────────────────────────────────────
@dataclass
class Case:
    id: str
    plan_id: str
    kind: str  # clean | mutant
    operator: str
    target: str
    pr: int
    base: str
    head: str
    split: str
    gold: dict[str, str]
    label: str
    note: str = ""
    patch: str = ""

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "kind": self.kind,
            "operator": self.operator,
            "target": self.target,
            "pr": self.pr,
            "base": self.base,
            "head": self.head,
            "split": self.split,
            "gold": self.gold,
            "label": self.label,
            "note": self.note,
        }


def build_plan_cases(
    repo: Path, merge: Merge, questions: list[critic.Question], scratch: Path
) -> tuple[list[Case], str]:
    """The clean case and every mutant that fits, or ``([], reason)``."""
    paths = changed_paths(repo, merge.base, merge.head)
    if not paths:
        return [], "empty diff"
    if f"docs/plans/{merge.plan_id}.md" not in paths:
        return [], "the PR does not carry docs/plans/<id>.md"
    if touches_overlay(paths):
        return [], "the PR changes the critic's own files"
    clean, label = is_clean(repo, merge, paths)
    if not clean:
        return [], label
    split = calibration.split_of(merge.plan_id)
    common = {
        "plan_id": merge.plan_id,
        "pr": merge.pr,
        "base": merge.base,
        "head": merge.head,
        "split": split,
    }
    cases = [
        Case(
            id=merge.plan_id,
            kind="clean",
            operator="",
            target="",
            gold=gold_for(paths, questions),
            label=label,
            **common,
        )
    ]
    work = scratch / merge.plan_id
    git("worktree", "add", "-q", "--detach", str(work), merge.head, cwd=repo)
    try:
        tree = Tree.load(work, merge.plan_id, merge.base)
        for name, func in OPERATOR_FUNCS.items():
            mutation = func(tree)
            if mutation is None:
                git("reset", "-q", "--hard", "HEAD", cwd=work)
                git("clean", "-q", "-fd", cwd=work)
                continue
            patch, touched = capture_patch(work)
            if not patch.strip():
                continue
            mutant_paths = sorted(set(paths) | set(touched))
            gold = gold_for(mutant_paths, questions, target=mutation.question)
            if mutation.question not in gold:
                continue  # the question would not even be asked
            cases.append(
                Case(
                    id=f"{merge.plan_id}--{name.lower()}",
                    kind="mutant",
                    operator=name,
                    target=mutation.question,
                    gold=gold,
                    label=label,
                    note=mutation.note,
                    patch=patch,
                    **common,
                )
            )
    finally:
        git("worktree", "remove", "--force", str(work), cwd=repo, check=False)
    return cases, ""


def write_cases(repo: Path, cases: list[Case], out: Path) -> None:
    for case in cases:
        d = repo / out / case.id
        d.mkdir(parents=True, exist_ok=True)
        (d / "case.json").write_text(json.dumps(case.as_json(), indent=2) + "\n", encoding="utf-8")
        if case.patch:
            (d / "mutation.patch").write_text(case.patch, encoding="utf-8")


def load_cases(repo: Path, out: Path = CASES) -> list[dict[str, Any]]:
    """Every stored case, sorted by id."""
    return sorted(
        (json.loads(p.read_text(encoding="utf-8")) for p in (repo / out).glob("*/case.json")),
        key=lambda c: c["id"],
    )


def write_test_pin(repo: Path, out: Path = CASES) -> str:
    ids = [c["id"] for c in load_cases(repo, out) if c["split"] == "test"]
    digest = calibration.test_split_hash(ids)
    pin = repo / TEST_SPLIT_PIN
    pin.parent.mkdir(parents=True, exist_ok=True)
    pin.write_text(f"{digest}  {len(ids)} test cases\n", encoding="utf-8")
    return digest


def archived_plan_ids(repo: Path) -> list[str]:
    return sorted(p.stem for p in (repo / ARCHIVE).glob("*.md"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--max-plans", type=int, default=30, help="stop after this many usable plans")
    ap.add_argument("--plan", action="append", default=[], help="only these plan ids")
    ap.add_argument("--dry-run", action="store_true", help="build in a scratch dir, write nothing")
    ap.add_argument("--out", default=str(CASES))
    args = ap.parse_args(argv)

    repo = ROOT
    questions = critic.load_questions(repo)
    ids = args.plan or archived_plan_ids(repo)
    merges = find_merges(repo, ids)
    # newest first: today's critic questions fit recent plans best
    order = sorted(merges.values(), key=lambda m: m.merged_at, reverse=True)
    built: list[Case] = []
    used = 0
    with tempfile.TemporaryDirectory(prefix="kaleta-seed-") as tmp:
        for merge in order:
            if used >= args.max_plans:
                break
            cases, reason = build_plan_cases(repo, merge, questions, Path(tmp))
            if not cases:
                print(f"skip  {merge.plan_id:45} {reason}")
                continue
            used += 1
            built.extend(cases)
            ops = ", ".join(c.operator for c in cases if c.kind == "mutant") or "-"
            print(f"case  {merge.plan_id:45} {cases[0].split:5} #{merge.pr}  mutants: {ops}")
        git("worktree", "prune", cwd=repo, check=False)

    by_op: dict[str, int] = {}
    for c in built:
        if c.kind == "mutant":
            by_op[c.operator] = by_op.get(c.operator, 0) + 1
    split_n = {s: sum(1 for c in built if c.split == s) for s in ("calib", "test")}
    print(
        f"seed_defects: {used} plans, {len(built)} cases"
        f" (calib {split_n['calib']}, test {split_n['test']});"
        f" mutants per operator: {json.dumps(by_op, sort_keys=True)}"
    )
    print(f"seed_defects: plans without a recoverable merge: {len(ids) - len(merges)}")
    if args.dry_run:
        print("seed_defects: dry run — nothing written")
        return 0
    out = Path(args.out)
    if (repo / out).exists():
        shutil.rmtree(repo / out)
    write_cases(repo, built, out)
    digest = write_test_pin(repo, out)
    print(f"seed_defects: wrote {out}/ and {TEST_SPLIT_PIN} ({digest[:16]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
