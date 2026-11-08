# SPDX-License-Identifier: AGPL-3.0-or-later
"""The critic answers narrow questions; evidence is checked; p is the share of valid samples."""

from __future__ import annotations

import json
from pathlib import Path

import critic
import gate_log
import pytest
from conftest import HarnessRepo, answers, fake_samples

QS = [
    critic.Question("Q-SCOPE", "scope?"),
    critic.Question("Q-SERVICE-TEST", "test?", applies_to=("src/kaleta/services/*",)),
    critic.Question("Q-VIEW-LOGIC", "view?", applies_to=("src/kaleta/views/*",)),
]
CHANGED = {"src/kaleta/services/x.py", "docs/plans/p.md"}
NEW_LINES = {"src/kaleta/services/x.py": {10, 11, 12}, "docs/plans/p.md": {40}}


def _sample(*ans: dict) -> critic.Sample:
    return critic.Sample("claude", "sonnet", True, answers=list(ans))


# ── question selection ───────────────────────────────────────────────────
def test_questions_apply_by_path() -> None:
    picked = critic.applicable(QS, ["src/kaleta/services/x.py", "docs/plans/p.md"])
    assert [q.id for q in picked] == ["Q-SCOPE", "Q-SERVICE-TEST"]
    assert [q.id for q in critic.applicable(QS, ["docs/x.md"])] == ["Q-SCOPE"]


def test_the_repo_question_set_loads_and_is_unique() -> None:
    qs = critic.load_questions(Path(critic.__file__).resolve().parents[2])
    ids = [q.id for q in qs]
    assert len(ids) == len(set(ids)) >= 10
    assert all(q.text and q.section for q in qs)


# ── evidence ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("file", "line", "ok"),
    [
        ("src/kaleta/services/x.py", 11, True),
        ("src/kaleta/services/x.py", 16, True),  # within the ±5 window
        ("src/kaleta/services/x.py", 30, False),  # nowhere near a changed line
        ("./src/kaleta/services/x.py", 10, True),
        ("src/kaleta/services/other.py", 10, False),  # not in the diff
    ],
)
def test_evidence_must_point_into_the_diff(file: str, line: int, ok: bool) -> None:
    assert critic.evidence_ok({"file": file, "line": line}, CHANGED, NEW_LINES) is ok


def test_yes_without_valid_evidence_is_an_invalid_sample_not_a_violation() -> None:
    s = _sample(
        {"id": "Q-SCOPE", "answer": "yes", "evidence": [{"file": "src/nowhere.py", "line": 1}]},
        {"id": "Q-SERVICE-TEST", "answer": "yes"},
    )
    v = critic.validate(s, ["Q-SCOPE", "Q-SERVICE-TEST"], CHANGED, NEW_LINES)
    assert v["Q-SCOPE"].value is None
    assert "evidence" in v["Q-SCOPE"].invalid_reason
    assert v["Q-SERVICE-TEST"].value is None


def test_missing_or_malformed_answers_are_invalid() -> None:
    s = _sample({"id": "Q-SCOPE", "answer": "maybe"})
    v = critic.validate(s, ["Q-SCOPE", "Q-SERVICE-TEST"], CHANGED, NEW_LINES)
    assert v["Q-SCOPE"].invalid_reason == "answer 'maybe'"
    assert v["Q-SERVICE-TEST"].invalid_reason == "no answer"


# ── aggregation ──────────────────────────────────────────────────────────
def test_p_is_the_share_of_valid_samples_that_found_the_problem() -> None:
    yes = {
        "id": "Q-SERVICE-TEST",
        "answer": "yes",
        "evidence": [{"file": "src/kaleta/services/x.py", "line": 11}],
        "note": "no test for f()",
    }
    no = {"id": "Q-SERVICE-TEST", "answer": "no"}
    bad = {"id": "Q-SERVICE-TEST", "answer": "yes", "evidence": [{"file": "x", "line": 1}]}
    samples = [_sample(yes), _sample(yes), _sample(no), _sample(bad)]
    v = [critic.validate(s, ["Q-SERVICE-TEST"], CHANGED, NEW_LINES) for s in samples]
    (q,) = critic.aggregate([QS[1]], v)
    assert q["violations"] == 2
    assert q["k_valid"] == 3
    assert q["k_total"] == 4
    assert q["p_violation"] == pytest.approx(0.6667, abs=1e-4)
    assert q["evidence"] == [{"file": "src/kaleta/services/x.py", "line": 11}]
    assert q["notes"] == ["no test for f()", "no test for f()"]
    assert q["invalid"] == ["evidence does not point into the diff"]


def test_no_valid_sample_gives_no_probability() -> None:
    v = [critic.validate(_sample(), ["Q-SCOPE"], CHANGED, NEW_LINES)]
    (q,) = critic.aggregate([QS[0]], v)
    assert q["p_violation"] is None
    assert q["k_valid"] == 0


def test_critic_hash_changes_with_the_questions(tmp_path: Path) -> None:
    (tmp_path / "docs/harness").mkdir(parents=True)
    f = tmp_path / critic.QUESTIONS
    f.write_text('[[question]]\nid = "Q-A"\ntext = "a"\n')
    h1 = critic.critic_hash(tmp_path, ["sonnet"])
    f.write_text('[[question]]\nid = "Q-A"\ntext = "b"\n')
    assert critic.critic_hash(tmp_path, ["sonnet"]) != h1
    assert critic.critic_hash(tmp_path, ["opus"]) != critic.critic_hash(tmp_path, ["sonnet"])


# ── end to end (fake samples, real repo) ─────────────────────────────────
def _work(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\nY = 3\n")
    repo.commit("work")


def test_run_writes_critic_json_and_a_review_record(repo: HarnessRepo) -> None:
    _work(repo)
    fake = fake_samples(
        repo,
        [answers(Q_SCOPE=("yes", "src/app.py", 2)), answers(Q_SCOPE="no"), answers(Q_SCOPE="no")],
    )
    out = repo.run("scripts/review_gate.sh", env={"KALETA_CRITIC_FAKE": fake})
    assert out.returncode == 0, out.stderr
    c = json.loads(repo.state("critic.json") or "{}")
    assert c["status"] == "ok"
    assert c["diff_hash"] == repo.diff_hash()
    scope = next(q for q in c["questions"] if q["id"] == "Q-SCOPE")
    assert scope["p_violation"] == pytest.approx(0.3333, abs=1e-4)
    assert "verdict" not in c
    (rec,) = [r for r in gate_log.records(repo.root, "fixture") if r["kind"] == "review"]
    assert rec["cost_usd"] == pytest.approx(0.3)


def test_required_cross_family_sample_that_fails_is_an_error(repo: HarnessRepo) -> None:
    _work(repo)
    fake = fake_samples(repo, [answers(Q_SCOPE="no"), answers(Q_SCOPE="no")])  # no cross.json
    out = repo.run(
        "scripts/review_gate.sh", env={"KALETA_CRITIC_FAKE": fake, "KALETA_CROSS_REVIEW": "1"}
    )
    assert out.returncode == 1
    c = json.loads(repo.state("critic.json") or "{}")
    assert c["status"] == "error"
    assert c["error_kind"] == "cross_unavailable"


def test_cross_family_sample_counts_toward_k(repo: HarnessRepo) -> None:
    _work(repo)
    fake = fake_samples(
        repo,
        [answers(Q_SCOPE="no"), answers(Q_SCOPE="no")],
        cross=answers(Q_SCOPE=("yes", "src/app.py", 1)),
    )
    out = repo.run(
        "scripts/review_gate.sh", env={"KALETA_CRITIC_FAKE": fake, "KALETA_CROSS_REVIEW": "1"}
    )
    assert out.returncode == 0, out.stderr
    c = json.loads(repo.state("critic.json") or "{}")
    assert c["cross_family_present"] is True
    assert len(c["samples"]) == 3
    scope = next(q for q in c["questions"] if q["id"] == "Q-SCOPE")
    assert scope["violations"] == 1


def test_real_claude_output_is_parsed(repo: HarnessRepo) -> None:
    """The claude -p JSON envelope: structured_output, total_cost_usd, num_turns."""
    _work(repo)
    bindir = repo.root.parent / "bin"
    bindir.mkdir(exist_ok=True)
    payload = {"structured_output": answers(Q_SCOPE="no"), "total_cost_usd": 0.02, "num_turns": 4}
    claude = bindir / "claude"
    claude.write_text(f"#!/usr/bin/env bash\necho '{json.dumps(payload)}'\n")
    claude.chmod(0o755)
    out = repo.run(
        "scripts/review_gate.sh",
        env={"PATH": f"{bindir}:/usr/bin:/bin", "KALETA_CRITIC_SAMPLES": "4"},
    )
    assert out.returncode == 0, out.stderr
    c = json.loads(repo.state("critic.json") or "{}")
    assert [s["turns"] for s in c["samples"]] == [4, 4, 4, 4]  # env may raise k
    assert c["cost_usd"] == pytest.approx(0.08)


def test_dry_run_lists_questions_without_calling_anything(repo: HarnessRepo) -> None:
    _work(repo)
    out = repo.run("scripts/review_gate.sh", "--dry-run", env={"PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    assert "Q-SCOPE" in out.stdout
    assert "Q-SERVICE-TEST" not in out.stdout  # no service changed
    assert repo.state("critic.json") is None
