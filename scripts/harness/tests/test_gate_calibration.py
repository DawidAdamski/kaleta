# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which calibration report the gate accepts (plan critic-calibration-set).

A question is calibrated only by a report of the held-out test split, run to
the end, for the current critic hash, whose miss-rate upper bound is at or
below ``[calibration] miss_rate_target``. A calib-split report is tuned on, so
it never counts.
"""

from __future__ import annotations

import json
from pathlib import Path

import gate
import judge

REPORT = "docs/harness/calibration/abc-test.json"


def profile(report: str = REPORT, target: float = 0.10) -> judge.Profile:
    return judge.Profile(raw={"calibration": {"report": report, "miss_rate_target": target}})


def write(root: Path, **overrides: object) -> None:
    data = {
        "critic_hash": "abc",
        "split": "test",
        "complete": True,
        "questions": {
            "Q-SCOPE": {"miss_rate_upper": 0.08},
            "Q-NOTES-TRUTH": {"miss_rate_upper": 0.25},
            "Q-MIGRATION": {"miss_rate_upper": None},
        },
    }
    data.update(overrides)
    path = root / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_a_complete_test_report_calibrates_questions_under_the_target(tmp_path: Path) -> None:
    write(tmp_path)
    out = gate.calibration(tmp_path, profile(), "abc")
    assert out["usable"] is True
    assert out["critic_hash_match"] is True
    assert out["calibrated"] == ["Q-SCOPE"]


def test_another_critic_hash_calibrates_nothing(tmp_path: Path) -> None:
    write(tmp_path)
    out = gate.calibration(tmp_path, profile(), "changed")
    assert out["critic_hash_match"] is False
    assert out["calibrated"] == []


def test_a_calib_split_report_never_counts(tmp_path: Path) -> None:
    write(tmp_path, split="calib")
    out = gate.calibration(tmp_path, profile(), "abc")
    assert out["usable"] is False
    assert out["calibrated"] == []


def test_an_incomplete_test_run_does_not_count(tmp_path: Path) -> None:
    write(tmp_path, complete=False)
    assert gate.calibration(tmp_path, profile(), "abc")["calibrated"] == []


def test_no_report_configured_or_missing(tmp_path: Path) -> None:
    assert gate.calibration(tmp_path, profile(report=""), "abc")["calibrated"] == []
    assert gate.calibration(tmp_path, profile(), "abc")["calibrated"] == []


def test_a_list_of_reports_picks_the_one_for_this_critic(tmp_path: Path) -> None:
    write(tmp_path)  # abc
    other = "docs/harness/calibration/def-test.json"
    (tmp_path / other).write_text(
        json.dumps(
            {
                "critic_hash": "def",
                "split": "test",
                "complete": True,
                "questions": {"Q-MIGRATION": {"miss_rate_upper": 0.05}},
            }
        ),
        encoding="utf-8",
    )
    reports = judge.Profile(raw={"calibration": {"report": [REPORT, other]}})
    assert gate.calibration(tmp_path, reports, "def")["calibrated"] == ["Q-MIGRATION"]
    assert gate.calibration(tmp_path, reports, "def")["report"] == other
    assert gate.calibration(tmp_path, reports, "abc")["calibrated"] == ["Q-SCOPE"]
    assert gate.calibration(tmp_path, reports, "zzz")["calibrated"] == []
