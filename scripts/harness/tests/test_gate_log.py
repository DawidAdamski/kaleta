# SPDX-License-Identifier: AGPL-3.0-or-later
"""The run log is append-only and tamper-evident; report summarises it."""

from __future__ import annotations

import json
from pathlib import Path

import gate_log
import pytest


def _log(tmp_path: Path, n: int = 3) -> Path:
    for i in range(n):
        gate_log.append(
            tmp_path, "p1", "gate", {"attempt": i + 1, "outcome": "block", "dry": False}
        )
    return gate_log.log_path(tmp_path, "p1")


def test_chain_verifies(tmp_path: Path) -> None:
    path = _log(tmp_path)
    recs = gate_log.read(path)
    assert [r["seq"] for r in recs] == [1, 2, 3]
    assert recs[0]["prev"] == gate_log.GENESIS
    assert recs[1]["prev"] == recs[0]["sha"]
    assert gate_log.verify(tmp_path) == []


def test_edited_record_is_detected(tmp_path: Path) -> None:
    path = _log(tmp_path)
    lines = path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["outcome"] = "done"
    lines[1] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n")
    errors = gate_log.verify(tmp_path)
    assert any("modified" in e for e in errors)


def test_deleted_record_is_detected(tmp_path: Path) -> None:
    path = _log(tmp_path)
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n")
    errors = gate_log.verify(tmp_path)
    assert any("chain broken" in e for e in errors)
    assert any("deleted or reordered" in e for e in errors)


def test_rewritten_chain_from_scratch_still_needs_every_sha(tmp_path: Path) -> None:
    """Recomputing one sha is not enough: the next record's prev no longer matches."""
    path = _log(tmp_path)
    lines = path.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["outcome"] = "done"
    rec["sha"] = gate_log._sha(rec)
    lines[0] = gate_log.canonical(rec)
    path.write_text("\n".join(lines) + "\n")
    assert any("chain broken" in e for e in gate_log.verify(tmp_path))


def test_invalid_plan_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        gate_log.append(tmp_path, "../escape", "gate", {})
    with pytest.raises(ValueError):
        gate_log.append(tmp_path, "ok", "nonsense", {})


def test_report_summarises_outcomes_and_cost(tmp_path: Path) -> None:
    gate_log.append(tmp_path, "a", "review", {"cost_usd": 0.5})
    gate_log.append(tmp_path, "a", "gate", {"attempt": 1, "outcome": "block"})
    gate_log.append(tmp_path, "a", "review", {"cost_usd": 0.25})
    gate_log.append(tmp_path, "a", "gate", {"attempt": 2, "outcome": "done"})
    gate_log.append(tmp_path, "b", "gate", {"attempt": 1, "outcome": "exhausted"})
    gate_log.append(tmp_path, "b", "gate", {"attempt": 1, "outcome": "block", "dry": True})
    text = gate_log.report(tmp_path)
    assert "outcomes: done 1, exhausted 1" in text
    assert "critic cost per done plan: 0.75 USD" in text
    row_a = next(line for line in text.splitlines() if line.startswith("a "))
    assert " 2 " in row_a  # attempts
    assert "0.75" in row_a


def test_cli_append_and_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    payload = tmp_path / "p.json"
    payload.write_text('{"verdict": "approve"}')
    assert (
        gate_log.main(
            ["--root", str(tmp_path), "append", "x", "--kind", "review", "--json", str(payload)]
        )
        == 0
    )
    assert gate_log.main(["--root", str(tmp_path), "verify"]) == 0
    assert "OK" in capsys.readouterr().out
