# SPDX-License-Identifier: AGPL-3.0-or-later
"""Git helpers shared by the gate, the critic and the run log (ADR-39).

The diff under judgement is ``git diff <merge-base>`` (working tree
included). Run logs under ``docs/harness/runs/`` are written by the harness
itself, so they are excluded from the diff hash: appending a log line must not
make a review stale.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

RUNS_PATHSPEC = ":(exclude)docs/harness/runs/**"


def git(*args: str, check: bool = True, cwd: Path | None = None) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace", check=False
    )
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def toplevel() -> Path:
    try:
        return Path(git("rev-parse", "--show-toplevel").strip())
    except RuntimeError:
        return Path.cwd()


def merge_base(ref: str = "main") -> str:
    try:
        return git("merge-base", "HEAD", ref).strip()
    except RuntimeError:
        return ref


def branch() -> str:
    try:
        return git("rev-parse", "--abbrev-ref", "HEAD").strip()
    except RuntimeError:
        return ""


def diff_text(base: str) -> str:
    return git("diff", base, "--", ".", RUNS_PATHSPEC, check=False)


def diff_hash(base: str) -> str:
    return hashlib.sha256(diff_text(base).encode()).hexdigest()[:16]


def file_sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else None


@dataclass(frozen=True)
class Changed:
    path: str
    added: int | None
    removed: int | None
    untracked: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "added": self.added,
            "removed": self.removed,
            "untracked": self.untracked,
        }


def changed(base: str) -> list[Changed]:
    """Tracked changes against ``base`` plus untracked, non-ignored files."""
    out: dict[str, Changed] = {}
    for line in git("diff", "--numstat", base, check=False).splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, r, path = parts
        if " => " in path:  # rename: keep the new name
            path = path.split(" => ")[-1].replace("{", "").replace("}", "")
        out[path] = Changed(path, None if a == "-" else int(a), None if r == "-" else int(r))
    for path in git("ls-files", "--others", "--exclude-standard", check=False).splitlines():
        if path and path not in out:
            out[path] = Changed(path, None, None, untracked=True)
    return sorted(out.values(), key=lambda c: c.path)


@dataclass(frozen=True)
class DiffLine:
    path: str
    text: str
    new_line: int | None  # line number on the new side, for added lines


def diff_lines(base: str) -> tuple[list[DiffLine], list[DiffLine]]:
    """Added and removed lines of ``git diff base``, with their files."""
    added: list[DiffLine] = []
    removed: list[DiffLine] = []
    path = ""
    new_no = 0
    for raw in git("diff", "-U0", base, check=False).splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else ""
            continue
        if raw.startswith("--- "):
            continue
        if raw.startswith("@@"):
            # @@ -a,b +c,d @@
            new = raw.split("+", 1)[1].split(" ", 1)[0]
            new_no = int(new.split(",")[0])
            continue
        if raw.startswith("+"):
            added.append(DiffLine(path, raw[1:], new_no))
            new_no += 1
        elif raw.startswith("-"):
            removed.append(DiffLine(path, raw[1:], None))
    return added, removed


def new_side_lines(base: str) -> dict[str, set[int]]:
    """Per changed file, the line numbers added or modified on the new side."""
    added, _ = diff_lines(base)
    lines: dict[str, set[int]] = {}
    for d in added:
        if d.path and d.new_line is not None:
            lines.setdefault(d.path, set()).add(d.new_line)
    return lines
