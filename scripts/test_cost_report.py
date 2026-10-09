#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where the test suite spends its time — per file and per test.

Runs pytest with ``--durations=0`` (serially, so the numbers are not skewed by
parallel load) or reads the output of such a run, and prints a Markdown report:
one row per test file (tests, total seconds, share spent in setup) and the
slowest tests. It is the evidence behind the ``slow`` marker and the audit in
``docs/plans/test-suite-speed.md``.

Usage::

    uv run python scripts/test_cost_report.py                  # tests/unit tests/integration
    uv run python scripts/test_cost_report.py tests/e2e -- -x  # other paths, extra pytest args
    uv run python scripts/test_cost_report.py --from run.txt   # a saved --durations=0 output
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_LINE = re.compile(r"^(?P<secs>\d+\.\d+)s (?P<phase>setup|call|teardown)\s+(?P<nodeid>\S+)")


@dataclass
class FileCost:
    """Accumulated seconds for one test file."""

    tests: set[str] = field(default_factory=set)
    setup: float = 0.0
    call: float = 0.0
    teardown: float = 0.0

    @property
    def total(self) -> float:
        return self.setup + self.call + self.teardown


class CostReport:
    """Parse ``--durations=0`` output and render the Markdown report."""

    def __init__(self, text: str) -> None:
        self.files: dict[str, FileCost] = defaultdict(FileCost)
        self.tests: dict[str, float] = defaultdict(float)
        for line in text.splitlines():
            match = _LINE.match(line.strip())
            if match is None:
                continue
            secs = float(match["secs"])
            nodeid = match["nodeid"]
            cost = self.files[nodeid.split("::", 1)[0]]
            cost.tests.add(nodeid)
            setattr(cost, match["phase"], getattr(cost, match["phase"]) + secs)
            self.tests[nodeid] += secs

    def render(self, top: int) -> str:
        if not self.tests:
            return "No durations found — was the run made with --durations=0?\n"
        grand = sum(cost.total for cost in self.files.values())
        lines = [
            f"**{len(self.tests)} tests, {grand:.1f} s** (sum of setup + call + teardown, serial).",
            "",
            "| File | Tests | Seconds | Share | Setup share |",
            "|---|---:|---:|---:|---:|",
        ]
        ranked = sorted(self.files.items(), key=lambda item: item[1].total, reverse=True)
        for path, cost in ranked[:top]:
            setup_share = cost.setup / cost.total if cost.total else 0.0
            lines.append(
                f"| `{path}` | {len(cost.tests)} | {cost.total:.1f} | "
                f"{cost.total / grand:.1%} | {setup_share:.0%} |"
            )
        lines += ["", f"Slowest {top} tests:", "", "| Seconds | Test |", "|---:|---|"]
        for nodeid, secs in sorted(self.tests.items(), key=lambda item: item[1], reverse=True)[
            :top
        ]:
            lines.append(f"| {secs:.2f} | `{nodeid}` |")
        return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("paths", nargs="*", default=["tests/unit", "tests/integration"])
    parser.add_argument("--from", dest="source", type=Path, help="read a saved run instead")
    parser.add_argument("--top", type=int, default=30, help="rows per table (default 30)")
    args, extra = parser.parse_known_args()
    extra = [arg for arg in extra if arg != "--"]

    if args.source is not None:
        text = args.source.read_text()
    else:
        command = [sys.executable, "-m", "pytest", *args.paths, "-q", "-p", "no:xdist"]
        command += ["--durations=0", "--durations-min=0", *extra]
        text = subprocess.run(command, capture_output=True, text=True, check=False).stdout
    sys.stdout.write(CostReport(text).render(args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
