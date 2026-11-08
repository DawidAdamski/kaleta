# SPDX-License-Identifier: AGPL-3.0-or-later
"""Python twin of ``scripts/harness/protected-lib.sh`` (ADR-39).

Reads ``docs/harness/protected-paths.txt``. ``*`` matches any characters
including ``/``, exactly like bash ``[[ $path == $glob ]]`` and
:func:`fnmatch.fnmatchcase`, so the hook and the gate agree.

    is_protected(rel, "edit", root)              -> the agent may not Edit/Write it
    is_protected(rel, "diff", root, base=sha)    -> a changed path that vetoes the diff
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Literal

LIST = Path("docs/harness/protected-paths.txt")
Kind = Literal["plain", "tracked", "harness"]
Mode = Literal["edit", "diff"]


@dataclass(frozen=True)
class Rule:
    kind: Kind
    glob: str


def load_rules(root: Path) -> list[Rule]:
    path = root / LIST
    if not path.exists():
        return []
    rules: list[Rule] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("tracked:"):
            rules.append(Rule("tracked", line.removeprefix("tracked:")))
        elif line.startswith("written-by-harness:"):
            rules.append(Rule("harness", line.removeprefix("written-by-harness:")))
        else:
            rules.append(Rule("plain", line))
    return rules


def _git_ok(root: Path, *args: str) -> bool:
    return (
        subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False).returncode
        == 0
    )


def is_protected(
    rel: str, mode: Mode, root: Path, base: str | None = None, rules: list[Rule] | None = None
) -> bool:
    for rule in load_rules(root) if rules is None else rules:
        if not fnmatchcase(rel, rule.glob):
            continue
        if rule.kind == "plain":
            return True
        if rule.kind == "harness":
            return mode == "edit"
        if mode == "edit":
            if _git_ok(root, "ls-files", "--error-unmatch", rel):
                return True
        elif base and _git_ok(root, "cat-file", "-e", f"{base}:{rel}"):
            return True
    return False


def protected_in_diff(paths: list[str], root: Path, base: str) -> list[str]:
    """The changed paths that veto a diff made outside maintainer mode."""
    rules = load_rules(root)
    return [p for p in paths if is_protected(p, "diff", root, base=base, rules=rules)]
