# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a plan file from docs/plans/ (shared by the gate and the critic)."""

from __future__ import annotations

import re
from typing import Any


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def plan_meta(text: str) -> dict[str, Any]:
    crit = section(text, "Acceptance criteria")
    commands = [
        m.group(1)
        for m in re.finditer(r"^- `([^`]*)`", crit, re.M)
        if not m.group(1).startswith("[manual]")
    ]
    title = re.search(r"^title:\s*(.*)$", text, re.M)
    return {
        "status_in_progress": bool(re.search(r"^status: in-progress", text, re.M)),
        "notes_filled": "_Filled in as work progresses._" not in text,
        "harness": bool(re.search(r"^harness:\s*true", text, re.M)),
        "title": title.group(1).strip() if title else "",
        "criteria": commands,
        "manual_criteria": len(re.findall(r"^- `?\[manual\]", crit, re.M)),
    }
