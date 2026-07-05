#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify relative markdown links and heading anchors resolve."""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
EXTRA_FILES = (
    ROOT / "README.md",
    ROOT / "CLAUDE.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
)

MARKDOWN_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")
FRONTMATTER_ROADMAP = re.compile(r"^roadmap_ref:\s*(.+)$", re.MULTILINE)
EXPLICIT_ANCHOR = re.compile(r"\{#([a-z0-9-]+)\}", re.IGNORECASE)
HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
SKIP_URL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:")


@dataclass(frozen=True)
class LinkRef:
    source: Path
    line_no: int
    target: str
    label: str


def slugify_heading(text: str) -> str:
    """GitHub / pymdownx-style heading slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-")


def collect_markdown_files() -> list[Path]:
    files = sorted(DOCS_DIR.rglob("*.md"))
    files.extend(p for p in EXTRA_FILES if p.is_file())
    return files


def heading_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line)
        if not match:
            continue
        title = match.group(2).strip()
        explicit = EXPLICIT_ANCHOR.search(title)
        if explicit:
            anchors.add(explicit.group(1).lower())
            title = EXPLICIT_ANCHOR.sub("", title).strip()
        slug = slugify_heading(title)
        if slug:
            anchors.add(slug)
    return anchors


def extract_links(path: Path) -> list[LinkRef]:
    text = path.read_text(encoding="utf-8")
    refs: list[LinkRef] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in MARKDOWN_LINK.finditer(line):
            refs.append(LinkRef(path, line_no, match.group(2).strip(), match.group(1)))
    if path.suffix == ".md" and "plans" in path.parts:
        in_frontmatter = False
        for line_no, line in enumerate(text.splitlines(), start=1):
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if not in_frontmatter:
                break
            roadmap_match = FRONTMATTER_ROADMAP.match(line)
            if roadmap_match:
                refs.append(LinkRef(path, line_no, roadmap_match.group(1).strip(), "roadmap_ref"))
    return refs


def split_target(raw: str) -> tuple[str | None, str | None]:
    target = raw.strip().strip("<>").split()[0]
    if target.startswith(SKIP_URL_PREFIXES):
        return None, None
    if "#" in target:
        path_part, anchor = target.split("#", 1)
        return path_part or None, anchor.lower() or None
    return target or None, None


def resolve_path(source: Path, path_part: str | None) -> Path | None:
    if path_part is None:
        return source
    candidate = (source.parent / path_part).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return candidate


def check_link(ref: LinkRef, anchor_cache: dict[Path, set[str]]) -> str | None:
    path_part, anchor = split_target(ref.target)
    if path_part is None and anchor is None:
        return None

    resolved = resolve_path(ref.source, path_part)
    if resolved is None:
        src = ref.source.relative_to(ROOT)
        return f"{src}:{ref.line_no}: external or out-of-repo link `{ref.target}`"

    if not resolved.is_file() and not resolved.is_dir():
        return (
            f"{ref.source.relative_to(ROOT)}:{ref.line_no}: "
            f"missing target `{path_part}` (from `{ref.target}`)"
        )

    if anchor is None:
        return None

    if resolved not in anchor_cache:
        anchor_cache[resolved] = heading_anchors(resolved)
    if anchor not in anchor_cache[resolved]:
        return (
            f"{ref.source.relative_to(ROOT)}:{ref.line_no}: "
            f"unknown anchor `#{anchor}` in {resolved.relative_to(ROOT)}"
        )
    return None


def main() -> int:
    files = collect_markdown_files()
    anchor_cache: dict[Path, set[str]] = {}
    errors: list[str] = []

    for path in files:
        for ref in extract_links(path):
            err = check_link(ref, anchor_cache)
            if err:
                errors.append(err)

    checked = sum(len(extract_links(p)) for p in files)
    print(f"Checked {checked} links across {len(files)} markdown files")

    if errors:
        print("\nBroken links:", file=sys.stderr)
        for err in sorted(errors):
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("OK: all relative links and anchors resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
