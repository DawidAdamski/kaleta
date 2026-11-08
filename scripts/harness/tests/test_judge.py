# SPDX-License-Identifier: AGPL-3.0-or-later
"""judge.decide is a pure function of the evidence and the owner's profile."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import gate_log
import judge
import pytest
from conftest import REPO

PROFILE = judge.load_profile(REPO)


def q(qid: str = "Q-SCOPE", p: float | None = 0.0, yes: int = 0, k: int = 3) -> dict[str, Any]:
    return {
        "id": qid,
        "p_violation": p,
        "violations": yes,
        "k_valid": k if p is not None else 0,
        "evidence": [{"file": "src/x.py", "line": 3}] if yes else [],
        "notes": [],
    }


def inputs(
    paths: tuple[str, ...] = ("src/kaleta/services/budget_service.py",),
    questions: list[dict] | None = None,
    **over: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "plan_id": "p",
        "plan": {"harness": False, "title": "T", "manual_criteria": 0, "exec_criteria": 2},
        "changed": [{"path": p} for p in paths],
        "diff_hash": "d1",
        "maintainer": False,
        "protected_touched": [],
        "green_washing": [],
        "secret_hits": [],
        "checks": [
            {
                "name": "verify.sh",
                "kind": "verify",
                "cmd": "./scripts/verify.sh",
                "ok": True,
                "tail": "",
            }
        ],
        "critic": {
            "present": True,
            "fresh": True,
            "status": "ok",
            "critic_hash": "c1",
            "cross_family_present": False,
            "samples_ok": 3,
            "questions": questions if questions is not None else [q()],
        },
        "prior_uncertain": {},
        "calibration": {"calibrated": []},
    }
    for k, v in over.items():
        if k in ("plan", "critic"):
            base[k] = base[k] | v
        else:
            base[k] = v
    return base


def codes(d: judge.Decision) -> list[str]:
    return [r["code"] for r in d.reasons]


# ── autonomy per change ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("paths", "plan", "cls", "mode"),
    [
        (("src/kaleta/services/budget_service.py",), {}, "medium", "B"),
        (("docs/guide.md",), {}, "low", "B"),  # A, capped while uncalibrated
        (("src/kaleta/auth/session.py",), {}, "high", "C"),
        (("alembic/versions/0042_x.py", "docs/a.md"), {}, "high", "C"),
        (("docs/guide.md",), {"exec_criteria": 0}, "high", "C"),
        (("docs/guide.md",), {"harness": True}, "high", "C"),
        (("docs/plans/p.md", "docs/harness/runs/p.jsonl"), {}, "low", "B"),  # ignored paths
    ],
)
def test_mode_follows_the_risk_class(paths, plan, cls, mode) -> None:
    d = judge.decide(inputs(paths, plan=plan), PROFILE)
    assert (d.outcome, d.risk_class, d.mode) == ("done", cls, mode)


def test_low_risk_is_capped_until_calibrated_then_a_label_only() -> None:
    capped = judge.decide(inputs(("docs/guide.md",)), PROFILE)
    assert capped.mode == "B"
    assert any("Capped at B" in w for w in capped.would_change)
    calibrated = judge.decide(
        inputs(("docs/guide.md",), calibration={"calibrated": ["Q-SCOPE"]}), PROFILE
    )
    assert calibrated.mode == "A"
    assert any("label only" in w for w in calibrated.warnings)


def test_high_risk_without_cross_family_sample_is_flagged() -> None:
    d = judge.decide(inputs(("src/kaleta/crypto/keys.py",)), PROFILE)
    assert d.mode == "C"
    assert any("cross-family" in w for w in d.warnings)
    with_cross = judge.decide(
        inputs(("src/kaleta/crypto/keys.py",), critic={"cross_family_present": True}), PROFILE
    )
    assert not any("cross-family" in w for w in with_cross.warnings)


# ── vetoes ───────────────────────────────────────────────────────────────
def test_protected_paths_escalate_to_d_unless_maintainer() -> None:
    d = judge.decide(inputs(protected_touched=["scripts/harness/judge.py"]), PROFILE)
    assert (d.outcome, d.mode, codes(d)) == ("escalate", "D", ["veto.protected"])
    m = judge.decide(
        inputs(protected_touched=["scripts/harness/judge.py"], maintainer=True), PROFILE
    )
    assert m.outcome == "done"


def test_secrets_escalate_to_d() -> None:
    d = judge.decide(inputs(secret_hits=["src/x.py:3"]), PROFILE)
    assert (d.outcome, d.mode) == ("escalate", "D")
    s = judge.decide(inputs(questions=[q("Q-SECRET-DATA", 0.33, 1)]), PROFILE)
    assert codes(s) == ["veto.secret_question"]


def test_vetoes_win_over_everything_else() -> None:
    d = judge.decide(
        inputs(
            protected_touched=["docs/harness/profile.toml"],
            checks=[{"name": "c", "kind": "criterion", "cmd": "false", "ok": False, "tail": "x"}],
        ),
        PROFILE,
    )
    assert d.outcome == "escalate"


# ── blockers ─────────────────────────────────────────────────────────────
def test_failed_checks_and_green_washing_block() -> None:
    d = judge.decide(
        inputs(
            checks=[
                {
                    "name": "c",
                    "kind": "criterion",
                    "cmd": "pytest x",
                    "ok": False,
                    "tail": "1 failed",
                }
            ],
            green_washing=[
                {"id": "skip-xfail", "outcome": "block", "message": "skip", "where": ["t.py:1"]},
                {"id": "type-ignore", "outcome": "warn", "message": "ignore", "where": ["s.py:2"]},
            ],
        ),
        PROFILE,
    )
    assert d.outcome == "block"
    assert codes(d) == ["check.criterion", "green_washing.skip-xfail"]
    assert any("ignore" in w for w in d.warnings)


@pytest.mark.parametrize(
    ("critic", "code"),
    [
        ({"present": False}, "critic.missing"),
        ({"fresh": False}, "critic.stale"),
        ({"status": "error", "error_kind": "no_samples", "error": "x"}, "critic.error"),
    ],
)
def test_missing_stale_or_broken_critic_blocks(critic, code) -> None:
    d = judge.decide(inputs(critic=critic), PROFILE)
    assert (d.outcome, codes(d)) == ("block", [code])


def test_unavailable_cross_family_sample_escalates() -> None:
    d = judge.decide(
        inputs(critic={"status": "error", "error_kind": "cross_unavailable", "error": "no CLI"}),
        PROFILE,
    )
    assert (d.outcome, d.mode, codes(d)) == ("escalate", "C", ["critic.cross_unavailable"])


def test_majority_blocks_and_tenant_isolation_blocks_on_one_sample() -> None:
    d = judge.decide(inputs(questions=[q("Q-SCOPE", 0.6667, 2)]), PROFILE)
    assert codes(d) == ["critic.block.Q-SCOPE"]
    t = judge.decide(inputs(questions=[q("Q-TENANT-ISOLATION", 0.3333, 1)]), PROFILE)
    assert codes(t) == ["critic.block.Q-TENANT-ISOLATION"]


def test_uncertainty_gets_one_round_then_goes_to_the_owner() -> None:
    first = judge.decide(inputs(questions=[q("Q-SCOPE", 0.3333, 1)]), PROFILE)
    assert (first.outcome, codes(first)) == ("block", ["critic.uncertain.Q-SCOPE"])
    second = judge.decide(
        inputs(questions=[q("Q-SCOPE", 0.3333, 1)], prior_uncertain={"Q-SCOPE": 1}), PROFILE
    )
    assert (second.outcome, second.mode) == ("escalate", "C")
    assert codes(second) == ["critic.uncertain_exhausted.Q-SCOPE"]


def test_blockers_come_before_escalation() -> None:
    d = judge.decide(
        inputs(
            questions=[q("Q-SCOPE", 0.3333, 1), q("Q-VIEW-LOGIC", 1.0, 3)],
            prior_uncertain={"Q-SCOPE": 1},
        ),
        PROFILE,
    )
    assert d.outcome == "block"
    assert codes(d) == ["critic.block.Q-VIEW-LOGIC"]


def test_question_without_a_valid_answer_blocks() -> None:
    d = judge.decide(inputs(questions=[q("Q-SCOPE", None)]), PROFILE)
    assert codes(d) == ["critic.no_answer.Q-SCOPE"]


# ── purity, profile, replay ──────────────────────────────────────────────
def test_decide_is_pure_and_serialisable() -> None:
    i = inputs(questions=[q("Q-SCOPE", 0.3333, 1)])
    frozen = copy.deepcopy(i)
    a = judge.decide(i, PROFILE).as_dict()
    b = judge.decide(json.loads(json.dumps(i)), judge.validate(json.loads(json.dumps(PROFILE.raw))))
    assert a == b.as_dict()
    assert i == frozen


@pytest.mark.parametrize(
    ("mutate", "msg"),
    [
        (lambda r: r["meta"].pop("signed"), "unsigned"),
        (lambda r: r["thresholds"].update(uncertain=0.9), "uncertain <= block"),
        (lambda r: r["autonomy"].update(low="D"), "A, B or C"),
        (lambda r: r["autonomy"].update(allow_auto_merge="yes"), "bool"),
    ],
)
def test_profile_validation(mutate, msg) -> None:
    raw = copy.deepcopy(PROFILE.raw)
    mutate(raw)
    with pytest.raises(judge.ProfileError, match=msg):
        judge.validate(raw)


def test_repo_profile_is_valid_and_conservative() -> None:
    assert PROFILE.autonomy["allow_auto_merge"] is False
    assert PROFILE.autonomy["uncalibrated_cap"] == "B"
    assert PROFILE.raw["calibration"]["report"] == ""


def test_replay_reproduces_recorded_decisions_and_catches_edits(tmp_path: Path) -> None:
    for i in (inputs(), inputs(questions=[q("Q-SCOPE", 0.6667, 2)])):
        gate_log.append(
            tmp_path,
            "p",
            "gate",
            {"inputs": i, "profile": PROFILE.raw, "decision": judge.decide(i, PROFILE).as_dict()},
        )
    gate_log.append(
        tmp_path, "p", "gate", {"inputs": {}, "decision": {"outcome": "block"}}
    )  # pre-judge
    log = gate_log.log_path(tmp_path, "p")
    checked, skipped, bad = judge.replay(log)
    assert (checked, skipped, bad) == (2, 1, [])

    lines = log.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["decision"]["mode"] = "A"
    lines[0] = json.dumps(rec)
    log.write_text("\n".join(lines) + "\n")
    assert judge.replay(log)[2]


def test_note_for_the_owner() -> None:
    i = inputs(("src/kaleta/auth/session.py",))
    note = judge.render_note(judge.decide(i, PROFILE), i, PROFILE.raw["meta"])
    assert "**Done — mode C**" in note
    assert "Risk class: **high** (src/kaleta/auth/session.py)" in note
    assert "| Q-SCOPE | 0.00 | 0 / 3 | - | - |" in note
    assert "Profile v1" in note
