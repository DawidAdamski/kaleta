# SPDX-License-Identifier: AGPL-3.0-or-later
"""Diffs the gate must survive and ways around it that must stay closed (ultrareview)."""

from __future__ import annotations

import json

from conftest import HarnessRepo


def _reason(out) -> str:
    return json.loads(out.stdout)["reason"] if out.stdout.strip() else ""


def test_non_utf8_content_in_the_diff_does_not_crash_the_gate(repo: HarnessRepo) -> None:
    repo.new_plan()
    # a cp1250 bank export, as a test fixture might be
    (repo.root / "tests").mkdir(exist_ok=True)
    (repo.root / "tests/bank_export.csv").write_bytes(
        "Data;Opis\n2026-01-02;Zażółć gęślą\n".encode("cp1250")
    )
    repo.commit("cp1250 fixture")
    out = repo.gate()
    reason = _reason(out)
    assert "crashed" not in reason
    assert "No critic run yet" in reason
