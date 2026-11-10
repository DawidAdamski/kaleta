# SPDX-License-Identifier: AGPL-3.0-or-later
"""The stored calibration cases never leak a plan across splits (plan critic-calibration-set).

A plan and all its variants (the clean case and every mutant) sit in one
split, decided by the plan id alone; the test split is the one pinned by
``docs/harness/calibration/test-split.sha256``.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import calibration
import seed_defects

REPO = Path(__file__).resolve().parents[3]


def _cases() -> list[dict]:
    cases = seed_defects.load_cases(REPO)
    assert cases, "no calibration cases under tests/harness/critic_cases/"
    return cases


def test_every_plan_sits_in_one_split() -> None:
    splits: dict[str, set[str]] = defaultdict(set)
    for case in _cases():
        splits[case["plan_id"]].add(case["split"])
    leaking = {plan: s for plan, s in splits.items() if len(s) != 1}
    assert leaking == {}


def test_the_split_is_the_plan_ids() -> None:
    wrong = [c["id"] for c in _cases() if c["split"] != calibration.split_of(c["plan_id"])]
    assert wrong == []


def test_both_splits_are_populated() -> None:
    assert {c["split"] for c in _cases()} == {"calib", "test"}


def test_every_mutant_has_its_clean_case() -> None:
    clean = {c["plan_id"] for c in _cases() if c["kind"] == "clean"}
    orphans = [c["id"] for c in _cases() if c["kind"] == "mutant" and c["plan_id"] not in clean]
    assert orphans == []


def test_the_test_split_matches_its_pin() -> None:
    pin = (REPO / seed_defects.TEST_SPLIT_PIN).read_text(encoding="utf-8").split()[0]
    ids = [c["id"] for c in _cases() if c["split"] == "test"]
    assert calibration.test_split_hash(ids) == pin


def test_split_of_is_stable_and_near_its_share() -> None:
    ids = [f"plan-{i}" for i in range(2000)]
    first = [calibration.split_of(i) for i in ids]
    assert first == [calibration.split_of(i) for i in ids]
    share = first.count("calib") / len(first)
    assert 0.66 < share < 0.74


def test_test_split_hash_ignores_order_and_duplicates() -> None:
    assert calibration.test_split_hash(["b", "a", "a"]) == calibration.test_split_hash(["a", "b"])
    assert calibration.test_split_hash(["a"]) != calibration.test_split_hash(["a", "b"])
