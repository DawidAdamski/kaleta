#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rewrite a plan's relative links for its move from ``docs/plans/`` to ``docs/plans/archive/``.

``scripts/plan_archive.sh`` calls this on the plan just before ``git mv``. The plan moves
one directory down, so every relative target that pointed out of ``docs/plans/`` needs one
more ``../``. Image links (``![alt](target)``) move under the same rules as ``[label]``
links. The archiver used to skip them, which left three archived plans pointing at
``docs/plans/images/`` and broke ``mkdocs build --strict`` (plan ``archive-image-links``).

Stdlib only: the archiver runs it with the system ``python3``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: ``[label](target)`` or ``![alt](target)``; group 1 is the ``!`` when it is an image.
LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
ROADMAP_REF = re.compile(r"^(roadmap_ref:\s*)\.\./", re.MULTILINE)
SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:", "#")


class PlanLinkRewriter:
    """Repoints one plan's relative links for the move into ``archive/``."""

    def __init__(self, plans_dir: Path) -> None:
        self.plans_dir = plans_dir
        self.archive_dir = plans_dir / "archive"

    def rewrite(self, text: str) -> str:
        text = ROADMAP_REF.sub(r"\1../../", text, count=1)
        return LINK.sub(self._fix, text)

    def _fix(self, match: re.Match[str]) -> str:
        bang, label, target = match.group(1), match.group(2), match.group(3)
        new_target = self._new_target(target)
        if new_target is None:
            return match.group(0)
        return f"{bang}[{label}]({new_target})"

    def _new_target(self, target: str) -> str | None:
        if target.startswith(SKIP_PREFIXES):
            return None
        if target.startswith("archive/"):
            return target[len("archive/") :]
        if target.startswith("../"):
            return f"../{target}"
        base = target.split("#")[0]
        if "/" not in base:
            if (self.archive_dir / base).exists():
                return None  # already a sibling in archive/
            if (self.plans_dir / base).exists():
                return f"../{target}"
        return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: plan_links.py <docs/plans/plan.md>", file=sys.stderr)
        return 2
    plan = Path(argv[1])
    rewriter = PlanLinkRewriter(plan.parent)
    plan.write_text(rewriter.rewrite(plan.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
