#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ensure AGPL SPDX headers on Python source files (idempotent --fix)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPDX_LINE = "# SPDX-License-Identifier: AGPL-3.0-or-later"
SPDX_PREFIX = f"{SPDX_LINE}\n"
SCAN_ROOTS = ("src/kaleta", "tests", "scripts")
SHEBANG_RE = re.compile(r"^#!.*\n")
ENCODING_RE = re.compile(r"^#.*coding[=:]\s*[-\w.]+\n")


def _has_spdx_header(content: str) -> bool:
    for line in content.splitlines()[:5]:
        if "SPDX-License-Identifier: AGPL-3.0-or-later" in line:
            return True
    return False


def _insert_spdx(content: str) -> str:
    if _has_spdx_header(content):
        return content

    pos = 0
    if match := SHEBANG_RE.match(content):
        pos = match.end()
    if match := ENCODING_RE.match(content[pos:]):
        pos += match.end()

    return content[:pos] + SPDX_PREFIX + content[pos:]


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for rel in SCAN_ROOTS:
        root = ROOT / rel
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Add missing SPDX headers (default: check only)",
    )
    args = parser.parse_args()

    missing: list[Path] = []
    for path in iter_python_files():
        original = path.read_text(encoding="utf-8")
        if _has_spdx_header(original):
            continue
        if args.fix:
            path.write_text(_insert_spdx(original), encoding="utf-8")
        else:
            missing.append(path)

    if missing:
        print("Missing SPDX header:", file=sys.stderr)
        for path in missing:
            print(f"  {path.relative_to(ROOT)}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
