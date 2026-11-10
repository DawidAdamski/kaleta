# SPDX-License-Identifier: AGPL-3.0-or-later
"""Calibration arithmetic for the critic (ADR-39 principle 5, plan critic-calibration-set).

Pure functions, no git and no model: the split a plan belongs to, the hash
that pins the test split, and the per-question metrics a calibration report
carries. ``seed_defects.py`` builds the cases, ``calibrate_critic.py`` runs
the critic on them and calls :func:`question_metrics`.

Gold labels are binary: ``yes`` (the problem is present) or ``no``. A critic
answer of ``na`` counts as "not yes", the same way ``p_violation`` counts it.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

#: Share of plans that go to the calibration split; the rest is the test split.
CALIB_SHARE = 0.70
#: z for a two-sided 95% interval.
Z95 = 1.959963984540054


# ── splits ───────────────────────────────────────────────────────────────
def split_of(plan_id: str, calib_share: float = CALIB_SHARE) -> str:
    """``calib`` or ``test`` for a plan — decided by the plan id alone.

    Every case built from one plan (the clean case and all its mutants) carries
    the same plan id, so a plan never leaks across splits.
    """
    digest = hashlib.sha256(plan_id.encode()).hexdigest()
    return "calib" if int(digest[:8], 16) / 0x1_0000_0000 < calib_share else "test"


def test_split_hash(case_ids: Iterable[str]) -> str:
    """The pin written to ``docs/harness/calibration/test-split.sha256``."""
    return hashlib.sha256("\n".join(sorted(set(case_ids))).encode()).hexdigest()


# ── intervals and scores ─────────────────────────────────────────────────
def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion; ``None`` when ``n`` is 0."""
    if n <= 0:
        return None
    phat = successes / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def brier(pairs: list[tuple[float, int]]) -> float | None:
    """Mean squared distance between ``p`` and the 0/1 gold label."""
    if not pairs:
        return None
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def reliability(pairs: list[tuple[float, int]], k: int) -> list[dict[str, Any]]:
    """One row per level ``j/k`` a k-sample critic can reach.

    ``p`` values are snapped to the nearest level (a sample that came back
    invalid makes ``2/2`` possible where ``2/3`` was expected).
    """
    levels = [j / k for j in range(k + 1)]
    rows: list[dict[str, Any]] = []
    for level in levels:
        members = [(p, y) for p, y in pairs if _nearest(p, levels) == level]
        n = len(members)
        rows.append(
            {
                "level": round(level, 4),
                "n": n,
                "mean_p": sum(p for p, _ in members) / n if n else None,
                "observed": sum(y for _, y in members) / n if n else None,
            }
        )
    return rows


def ece(rows: list[dict[str, Any]]) -> float | None:
    """Expected calibration error over the reliability rows."""
    total = sum(r["n"] for r in rows)
    if not total:
        return None
    return sum(r["n"] / total * abs(r["mean_p"] - r["observed"]) for r in rows if r["n"])


def _nearest(p: float, levels: list[float]) -> float:
    # rounded distance: 0.5 is exactly between 1/3 and 2/3, and the lower level wins
    return min(levels, key=lambda level: (round(abs(level - p), 9), level))


# ── per-question metrics ─────────────────────────────────────────────────
@dataclass
class Observation:
    """One question on one case: the gold label and what the critic said."""

    case_id: str
    plan_id: str
    question: str
    gold: str  # yes | no
    p: float | None  # p_violation; None when no sample answered validly
    samples: int = 0
    invalid: int = 0
    #: the mutant's operator target, or "" on a clean case
    target: str = ""
    kind: str = "clean"  # clean | mutant


@dataclass
class Thresholds:
    block: float
    uncertain: float


def rate(num: int, den: int) -> dict[str, Any]:
    interval = wilson(num, den)
    return {
        "value": round(num / den, 4) if den else None,
        "num": num,
        "den": den,
        "lower": round(interval[0], 4) if interval else None,
        "upper": round(interval[1], 4) if interval else None,
    }


def question_metrics(obs: list[Observation], thresholds: Thresholds, k: int) -> dict[str, Any]:
    """Metrics for one question.

    - **miss**: a true violation whose ``p`` stays under ``uncertain`` — it
      passes the gate without anyone looking (KPI number one). A violation with
      no valid sample counts as a miss: nothing stopped it.
    - **false alarm**: a clean answer whose ``p`` reaches ``block``.
    - **accuracy**: ``p >= block`` agrees with the gold label.
    - **flip**: on a (clean, mutant) pair whose mutation targets this
      question, ``p`` rose from the clean case to the mutant.
    """
    yes = [o for o in obs if o.gold == "yes"]
    no = [o for o in obs if o.gold == "no"]

    def p0(o: Observation) -> float:
        return 0.0 if o.p is None else o.p

    misses = sum(1 for o in yes if p0(o) < thresholds.uncertain)
    caught_block = sum(1 for o in yes if p0(o) >= thresholds.block)
    false_alarms = sum(1 for o in no if p0(o) >= thresholds.block)
    correct = sum(1 for o in obs if (p0(o) >= thresholds.block) == (o.gold == "yes"))
    pairs = [(p0(o), 1 if o.gold == "yes" else 0) for o in obs]
    rows = reliability(pairs, k)
    calib_error = ece(rows)
    samples = sum(o.samples for o in obs)
    invalid = sum(o.invalid for o in obs)

    clean_by_plan = {o.plan_id: o for o in obs if o.kind == "clean"}
    flips = [
        (clean_by_plan[o.plan_id], o)
        for o in obs
        if o.kind == "mutant" and o.target == o.question and o.plan_id in clean_by_plan
    ]
    moved = sum(1 for clean, mutant in flips if p0(mutant) > p0(clean))
    score = brier(pairs)

    return {
        "n": len(obs),
        "violations": len(yes),
        "clean": len(no),
        "accuracy": rate(correct, len(obs)),
        "miss_rate": rate(misses, len(yes)),
        "miss_rate_upper": rate(misses, len(yes))["upper"],
        "block_recall": rate(caught_block, len(yes)),
        "false_alarm_rate": rate(false_alarms, len(no)),
        "brier": round(score, 4) if score is not None else None,
        "reliability": rows,
        "ece": round(calib_error, 4) if calib_error is not None else None,
        "flip_rate": rate(moved, len(flips)),
        "invalid_evidence_rate": rate(invalid, samples),
        "no_valid_sample": sum(1 for o in obs if o.p is None),
    }
