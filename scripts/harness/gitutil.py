# SPDX-License-Identifier: AGPL-3.0-or-later
"""Git helpers shared by the gate, the critic and the run log (ADR-39).

The diff under judgement is ``git diff <merge-base>`` (working tree
included) plus every untracked, non-ignored file (``full_diff``). Run logs
under ``docs/harness/runs/`` are written by the harness itself, so they are
excluded from the diff hash: appending a log line must not make a review stale.
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


def untracked() -> list[str]:
    """Untracked, non-ignored files (minus the harness's own run logs)."""
    return [
        p
        for p in git("ls-files", "--others", "--exclude-standard", check=False).splitlines()
        if p and not p.startswith("docs/harness/runs/")
    ]


def full_diff(base: str, unified: int = 3) -> str:
    """``git diff base`` plus every untracked file as a diff against /dev/null.

    Untracked files are part of the change under judgement: the secret and
    green-washing scans, the critic's freshness hash and the critic's own
    prompt must see their content, not only their names.
    """
    tracked = git(
        "diff", "--no-renames", f"-U{unified}", base, "--", ".", RUNS_PATHSPEC, check=False
    )  # fmt: skip
    extra = [
        git("diff", "--no-index", f"-U{unified}", "--", "/dev/null", p, check=False)
        for p in untracked()
    ]
    return tracked + "".join(extra)


def diff_text(base: str) -> str:
    return full_diff(base)


def diff_hash(base: str) -> str:
    return hashlib.sha256(diff_text(base).encode()).hexdigest()[:16]


def read_at(root: Path, base: str | None, rel: str | Path) -> str | None:
    """``rel`` as it is on ``base``; the working tree only when ``base`` lacks it.

    The one way the harness reads the owner's law (profile, protected paths) for
    a diff: what is merged wins, even when it is empty. The working tree counts
    only for a file that is new in the diff, or when no ``base`` is given
    (maintainer sessions). ``None`` when neither has it.
    """
    rel = Path(rel).as_posix()
    if base:
        out = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{base}:{rel}"],
            capture_output=True,
            check=False,
        )
        if out.returncode == 0:
            return git("show", f"{base}:{rel}", cwd=root)
    path = root / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


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
    # --no-renames: a move is a deletion of the old path plus an addition of the
    # new one, so both are judged (a protected file moved out, a file moved into
    # a high-risk folder). Rename notation ("{a => b}") is never parsed.
    for line in git("diff", "--no-renames", "--numstat", base, check=False).splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, r, path = parts
        out[path] = Changed(path, None if a == "-" else int(a), None if r == "-" else int(r))
    for path in untracked():
        if path not in out:
            out[path] = Changed(path, None, None, untracked=True)
    return sorted(out.values(), key=lambda c: c.path)


@dataclass(frozen=True)
class DiffLine:
    path: str
    text: str
    new_line: int | None  # line number on the new side, for added lines


def diff_lines(base: str) -> tuple[list[DiffLine], list[DiffLine]]:
    """Added and removed lines of the change (``full_diff``), with their files."""
    added: list[DiffLine] = []
    removed: list[DiffLine] = []
    path = old_path = ""
    new_no = 0
    for raw in full_diff(base, unified=0).splitlines():
        if raw.startswith("--- "):
            old_path = raw[6:] if raw.startswith("--- a/") else ""
            continue
        if raw.startswith("+++ "):
            # a deleted file has "+++ /dev/null": its removed lines belong to the old path
            path = raw[6:] if raw.startswith("+++ b/") else old_path
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
