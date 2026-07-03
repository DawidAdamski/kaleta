#!/usr/bin/env python3
"""Check BDD scenario coverage against e2e and integration test docstrings."""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BDD_MD = ROOT / "docs" / "bdd.md"
TEST_DIRS = (ROOT / "tests" / "e2e", ROOT / "tests" / "integration")

SCENARIO_ID = re.compile(r"KAL-[A-Z]{3}-\d{3}")
TAG_LINE = re.compile(r"^\s*(KAL-[A-Z]{3}-\d{3})\s+@(automated|manual)\s*$")
FEATURE_HEADER = re.compile(r"^## Feature:\s*(.+)$")
COVERS_LINE = re.compile(r"^\s*Covers:\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    tag: str
    feature: str


def parse_bdd(path: Path = BDD_MD) -> tuple[dict[str, Scenario], list[str]]:
    """Return scenario map and parse errors (duplicate IDs)."""
    text = path.read_text(encoding="utf-8")
    current_feature = ""
    scenarios: dict[str, Scenario] = {}
    errors: list[str] = []
    pending_tag: tuple[str, str] | None = None

    for line_no, line in enumerate(text.splitlines(), start=1):
        feature_match = FEATURE_HEADER.match(line)
        if feature_match:
            current_feature = feature_match.group(1).strip()
            pending_tag = None
            continue

        tag_match = TAG_LINE.match(line)
        if tag_match:
            pending_tag = (tag_match.group(1), tag_match.group(2))
            continue

        if line.strip().startswith("Scenario:"):
            if pending_tag is None:
                errors.append(f"{path}:{line_no}: Scenario missing ID/tag line above it")
                pending_tag = None
                continue
            scenario_id, tag = pending_tag
            if scenario_id in scenarios:
                errors.append(f"{path}:{line_no}: duplicate scenario ID {scenario_id}")
            else:
                scenarios[scenario_id] = Scenario(scenario_id, tag, current_feature)
            pending_tag = None

    return scenarios, errors


def _docstring_covers(docstring: str | None) -> set[str]:
    if not docstring or "Covers:" not in docstring:
        return set()
    found: set[str] = set()
    for match in COVERS_LINE.finditer(docstring):
        found.update(SCENARIO_ID.findall(match.group(1)))
    return found


def _collect_docstrings(path: Path) -> list[tuple[str, str | None]]:
    """Return (qualname, docstring) for module and test functions."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    items: list[tuple[str, str | None]] = []

    module_doc = ast.get_docstring(tree)
    if module_doc:
        items.append((path.name, module_doc))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_"):
                continue
            items.append((f"{path.name}::{node.name}", ast.get_docstring(node)))

    return items


def parse_test_coverage(test_dirs: tuple[Path, ...] = TEST_DIRS) -> tuple[set[str], list[str]]:
    """Return covered scenario IDs and unknown-ID errors."""
    covered: set[str] = set()
    errors: list[str] = []
    known_ids, _ = parse_bdd()

    for test_dir in test_dirs:
        if not test_dir.is_dir():
            continue
        for path in sorted(test_dir.glob("test_*.py")):
            for qualname, docstring in _collect_docstrings(path):
                ids = _docstring_covers(docstring)
                if not ids and docstring and "Covers:" in docstring:
                    errors.append(f"{qualname}: Covers line has no valid KAL-* IDs")
                for scenario_id in ids:
                    if scenario_id not in known_ids:
                        errors.append(f"{qualname}: unknown scenario ID {scenario_id}")
                    covered.add(scenario_id)

    return covered, errors


def print_summary(scenarios: dict[str, Scenario], covered: set[str]) -> None:
    by_feature: dict[str, list[Scenario]] = defaultdict(list)
    for scenario in scenarios.values():
        by_feature[scenario.feature].append(scenario)

    headers = ("Feature", "Automated", "Manual", "Covered", "Uncovered auto")
    rows: list[tuple[str, str, str, str, str]] = []
    totals = [0, 0, 0, 0]

    for feature in sorted(by_feature):
        items = sorted(by_feature[feature], key=lambda s: s.scenario_id)
        automated = [s for s in items if s.tag == "automated"]
        manual = [s for s in items if s.tag == "manual"]
        covered_auto = [s for s in automated if s.scenario_id in covered]
        uncovered_auto = len(automated) - len(covered_auto)
        rows.append(
            (
                feature,
                str(len(automated)),
                str(len(manual)),
                str(len(covered_auto)),
                str(uncovered_auto),
            )
        )
        totals[0] += len(automated)
        totals[1] += len(manual)
        totals[2] += len(covered_auto)
        totals[3] += uncovered_auto

    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))
    widths[0] = max(widths[0], len("TOTAL"))

    def fmt_row(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    print(fmt_row(headers))
    print(fmt_row(tuple("-" * w for w in widths)))
    for row in rows:
        print(fmt_row(row))
    print(fmt_row(tuple("-" * w for w in widths)))
    print(
        fmt_row(
            (
                "TOTAL",
                str(totals[0]),
                str(totals[1]),
                str(totals[2]),
                str(totals[3]),
            )
        )
    )


def main() -> int:
    scenarios, bdd_errors = parse_bdd()
    covered, test_errors = parse_test_coverage()
    errors = bdd_errors + test_errors

    uncovered_automated = sorted(
        s.scenario_id
        for s in scenarios.values()
        if s.tag == "automated" and s.scenario_id not in covered
    )
    for scenario_id in uncovered_automated:
        feature = scenarios[scenario_id].feature
        errors.append(f"uncovered @automated scenario {scenario_id} ({feature})")

    print_summary(scenarios, covered)

    if errors:
        print("\nErrors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"\nOK: {len(scenarios)} scenarios, {len(covered)} covered IDs referenced by tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
