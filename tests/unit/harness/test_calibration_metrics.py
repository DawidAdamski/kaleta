# SPDX-License-Identifier: AGPL-3.0-or-later
"""The arithmetic of a critic calibration report (plan critic-calibration-set).

Synthetic observations with hand-computed expectations: Wilson intervals,
Brier, the reliability table at the levels a k=3 critic reaches, ECE, and the
per-question rates — miss (a violation under ``uncertain``), false alarm (a
clean answer at or above ``block``), accuracy and the counterfactual flip.
"""

from __future__ import annotations

import calibrate_critic
import calibration
import pytest
from calibration import Observation, Thresholds

T = Thresholds(block=0.66, uncertain=0.33)


def obs(
    plan: str, gold: str, p: float | None, *, kind: str = "clean", target: str = ""
) -> Observation:
    return Observation(
        case_id=f"{plan}-{kind}", plan_id=plan, question="Q-X", gold=gold, p=p,
        samples=3, invalid=0, target=target, kind=kind,
    )  # fmt: skip


class TestWilson:
    def test_known_values(self) -> None:
        lower, upper = calibration.wilson(5, 10) or (0, 0)
        assert lower == pytest.approx(0.2366, abs=1e-4)
        assert upper == pytest.approx(0.7634, abs=1e-4)

    def test_zero_successes_still_has_an_upper_bound(self) -> None:
        lower, upper = calibration.wilson(0, 10) or (1, 1)
        assert lower == 0.0
        assert upper == pytest.approx(0.2775, abs=1e-4)

    def test_no_observations_has_no_interval(self) -> None:
        assert calibration.wilson(0, 0) is None


class TestScores:
    def test_brier(self) -> None:
        assert calibration.brier([(1.0, 1), (0.0, 0)]) == 0.0
        assert calibration.brier([(2 / 3, 1)]) == pytest.approx(1 / 9)
        assert calibration.brier([]) is None

    def test_reliability_has_one_row_per_reachable_level(self) -> None:
        rows = calibration.reliability([(0.0, 0), (1 / 3, 0), (2 / 3, 1), (1.0, 1)], k=3)
        assert [r["level"] for r in rows] == [0.0, 0.3333, 0.6667, 1.0]
        assert [r["n"] for r in rows] == [1, 1, 1, 1]

    def test_reliability_snaps_an_odd_p_to_the_nearest_level(self) -> None:
        # 2 valid samples of 3 can give 0.5: equally far from 1/3 and 2/3, the lower wins
        rows = calibration.reliability([(0.5, 1)], k=3)
        assert [r["n"] for r in rows] == [0, 1, 0, 0]

    def test_ece_is_zero_when_p_matches_the_observed_frequency(self) -> None:
        rows = calibration.reliability([(1.0, 1)] * 3 + [(0.0, 0)] * 3, k=3)
        assert calibration.ece(rows) == 0.0

    def test_ece_weights_each_level_by_its_share(self) -> None:
        # two at p=2/3 that were both violations: observed 1.0, off by 1/3; half the cases
        rows = calibration.reliability([(2 / 3, 1), (2 / 3, 1), (0.0, 0), (0.0, 0)], k=3)
        assert calibration.ece(rows) == pytest.approx(0.5 * (1 / 3))


class TestQuestionMetrics:
    @pytest.fixture
    def metrics(self) -> dict:
        data = [
            # violations (mutants of plans a-d, targeting this question)
            obs("a", "yes", 1.0, kind="mutant", target="Q-X"),
            obs("b", "yes", 2 / 3, kind="mutant", target="Q-X"),
            obs("c", "yes", 1 / 3, kind="mutant", target="Q-X"),  # escalates, not a miss
            obs("d", "yes", 0.0, kind="mutant", target="Q-X"),  # miss
            obs("e", "yes", None, kind="mutant", target="Q-X"),  # no valid sample: a miss
            # clean cases of the same plans
            obs("a", "no", 0.0),
            obs("b", "no", 2 / 3),  # false alarm, and the pair did not move
            obs("c", "no", 0.0),
            obs("d", "no", 0.0),
        ]
        return calibration.question_metrics(data, T, k=3)

    def test_counts(self, metrics: dict) -> None:
        assert (metrics["n"], metrics["violations"], metrics["clean"]) == (9, 5, 4)

    def test_miss_is_a_violation_under_uncertain(self, metrics: dict) -> None:
        assert (metrics["miss_rate"]["num"], metrics["miss_rate"]["den"]) == (2, 5)
        assert metrics["miss_rate"]["value"] == 0.4
        assert metrics["miss_rate_upper"] == metrics["miss_rate"]["upper"]
        assert metrics["no_valid_sample"] == 1

    def test_block_recall_and_false_alarms(self, metrics: dict) -> None:
        assert (metrics["block_recall"]["num"], metrics["block_recall"]["den"]) == (2, 5)
        assert (metrics["false_alarm_rate"]["num"], metrics["false_alarm_rate"]["den"]) == (1, 4)

    def test_accuracy_compares_p_at_block_with_gold(self, metrics: dict) -> None:
        # right: a, b (yes) and a, c, d (clean); wrong: c, d, e (yes) and b (clean)
        assert (metrics["accuracy"]["num"], metrics["accuracy"]["den"]) == (5, 9)

    def test_flip_counts_pairs_whose_p_rose(self, metrics: dict) -> None:
        # pairs a, b, c, d (e has no clean case); a and c rose, b and d did not
        assert (metrics["flip_rate"]["num"], metrics["flip_rate"]["den"]) == (2, 4)

    def test_brier_treats_no_valid_sample_as_zero(self, metrics: dict) -> None:
        expected = (0 + (1 / 3) ** 2 + (2 / 3) ** 2 + 1 + 1 + 0 + (2 / 3) ** 2 + 0 + 0) / 9
        assert metrics["brier"] == pytest.approx(expected, abs=1e-4)

    def test_invalid_evidence_rate(self) -> None:
        o = obs("a", "yes", 1.0)
        o.invalid = 1
        m = calibration.question_metrics([o], T, k=3)
        assert (m["invalid_evidence_rate"]["num"], m["invalid_evidence_rate"]["den"]) == (1, 3)

    def test_a_question_without_violations_has_no_miss_rate(self) -> None:
        m = calibration.question_metrics([obs("a", "no", 0.0)], T, k=3)
        assert m["miss_rate"]["value"] is None
        assert m["miss_rate_upper"] is None


class TestReport:
    """``calibrate_critic.build_report``: thresholds per question, totals summed."""

    def test_per_question_thresholds_and_calibrated_list(self) -> None:
        import judge

        profile = judge.Profile(
            raw={
                "thresholds": {
                    "block": 0.66,
                    "uncertain": 0.33,
                    "question": {"Q-TIGHT": {"block": 0.33, "uncertain": 0.01}},
                },
                "calibration": {"miss_rate_target": 0.5},
            }
        )

        def line(case: str, plan: str, q: str, gold: str, p: float) -> dict:
            return {
                "case_id": case, "plan_id": plan, "kind": "mutant", "operator": "M", "target": q,
                "gold": {q: gold}, "status": "ok", "cost_usd": 0.5,
                "answers": {q: {"p": p, "k_total": 3, "invalid": 0}},
            }  # fmt: skip

        results = [line(f"c{i}", f"p{i}", "Q-LOOSE", "yes", 1.0) for i in range(30)]
        # Q-TIGHT blocks at 1/3, so one sample of three stops the change
        results.append(line("t1", "p100", "Q-TIGHT", "yes", 1 / 3))
        report = calibrate_critic.build_report(
            results, chash="h", split="test", k=3, profile=profile, cases_total=31, forced=[]
        )
        assert report["questions"]["Q-TIGHT"]["thresholds"] == {"block": 0.33, "uncertain": 0.01}
        assert report["questions"]["Q-TIGHT"]["block_recall"]["num"] == 1  # 1/3 blocks here
        assert report["complete"] is True
        assert report["cost_usd"] == 15.5
        # Q-LOOSE: 0 misses of 30, upper bound ~0.11 <= 0.5; Q-TIGHT: 0 of 1, upper ~0.79
        assert report["calibrated"] == ["Q-LOOSE"]
        assert report["totals"]["block_recall"]["num"] == 31
        assert "Q-LOOSE" in calibrate_critic.render_md(report)
