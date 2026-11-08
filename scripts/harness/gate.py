#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The DoD gate behind the Stop hook ``.claude/hooks/dod-gate.sh`` (ADR-39).

Active only while ``.claude/state/active-plan`` exists. It collects the
evidence for the armed plan (checks, green-washing, protected paths, the
critic's answers pooled over every run on this diff, calibration), asks the
judge (``judge.decide``, a pure function of that evidence and the owner's
profile), writes a ``gate`` record with inputs, profile and decision to the
run log, writes ``.claude/state/decision.md``, and answers Claude Code:

- block     -> ``{"decision": "block", "reason": ...}``: keep working
- done      -> nothing on stdout; ``result=done``, ``mode=<A-C>``
- escalate  -> nothing on stdout; ``result=escalated``: the owner decides
- exhausted -> the last allowed attempt blocked; ``result=exhausted``

``DOD_GATE_DRY=1`` (``scripts/plan_goal.sh check``) judges without counting
an attempt or changing ``result``; the record is marked ``dry``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import traceback
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # the gate must not leave files in the protected harness dir
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_log  # noqa: E402
import gitutil  # noqa: E402
import judge  # noqa: E402
from planfile import plan_meta  # noqa: E402
from protected import protected_in_diff  # noqa: E402

STATE = Path(".claude/state")
DEFAULT_MAX = 6
CHECK_TAIL = 15
VERIFY_TAIL = 40

RULES_FOOTER = (
    "\nRules: do not ask questions — resolve open questions with the plan defaults and record "
    "them in Implementation notes. If you are truly blocked, run: "
    'scripts/plan_goal.sh block "<reason>".\n'
)


# ── state ────────────────────────────────────────────────────────────────
def read_state(name: str) -> str | None:
    path = STATE / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def write_state(name: str, value: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / name).write_text(value, encoding="utf-8")


# ── evidence ─────────────────────────────────────────────────────────────
def run_check(name: str, kind: str, cmd: str, tail: int) -> tuple[dict[str, Any], str]:
    t0 = time.monotonic()
    out = subprocess.run(
        ["bash", "-c", cmd], capture_output=True, text=True, errors="replace", check=False
    )
    text = (out.stdout + out.stderr).rstrip()
    check = {
        "name": name,
        "kind": kind,
        "cmd": cmd,
        "ok": out.returncode == 0,
        "seconds": round(time.monotonic() - t0, 2),
        "tail": "\n".join(text.splitlines()[-tail:]) if out.returncode else "",
    }
    return check, text


def _in(path: str, globs: list[str]) -> bool:
    return any(fnmatchcase(path, g) for g in globs)


def pattern_hits(base: str, raw_profile: dict[str, Any]) -> tuple[list[dict], list[str]]:
    """Green-washing hits and secret-pattern hits on the changed lines."""
    added, removed = gitutil.diff_lines(base)
    hits = []
    for g in raw_profile.get("green_washing", []):
        rx = re.compile(g["pattern"])
        pool = added if g["lines"] == "added" else removed
        found = [
            f"{d.path}:{d.new_line or '-'}"
            for d in pool
            if d.path
            and _in(d.path, g.get("paths", ["*"]))
            and not _in(d.path, g.get("exclude", []))
            and rx.search(d.text)
        ]
        if found:
            hits.append(
                {
                    "id": g["id"],
                    "outcome": g["outcome"],
                    "message": g["message"],
                    "where": found[:10],
                }
            )
    vetoes = raw_profile.get("vetoes", {})
    secret_rx = [re.compile(p) for p in vetoes.get("secret_patterns", [])]
    skip = vetoes.get("secret_exclude", [])
    secrets = [
        f"{d.path}:{d.new_line}"
        for d in added
        if d.path and not _in(d.path, skip) and any(rx.search(d.text) for rx in secret_rx)
    ]
    return hits, secrets[:10]


def _samples_ok(record: dict[str, Any]) -> int:
    if "samples_ok" in record:
        return int(record["samples_ok"] or 0)
    return sum(1 for s in record.get("samples", []) if s.get("ok"))


def critic_evidence(
    root: Path,
    plan_id: str,
    diff_hash: str,
    profile: judge.Profile | None,
    log_ok: bool = True,
) -> tuple[dict[str, Any], dict[str, int]]:
    """The critic's answers for this diff, pooled over every run on it, and prior uncertainty.

    Pooling means re-running the critic on an unchanged diff adds samples to
    one estimate instead of offering a fresh draw: re-rolling until a lucky
    sample comes up does not work.
    """
    path = STATE / "critic.json"
    if not path.exists():
        return {"present": False}, {}
    try:
        latest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "present": True,
            "fresh": False,
            "status": "error",
            "error": "critic.json unreadable",
        }, {}
    status = {
        "present": True,
        "fresh": latest.get("diff_hash") == diff_hash,
        "status": latest.get("status"),
        "error_kind": latest.get("error_kind", ""),
        "error": latest.get("error", ""),
        "critic_hash": latest.get("critic_hash"),
        "cross_family_present": bool(latest.get("cross_family_present")),
        "runs_pooled": 1,
        "samples_ok": _samples_ok(latest),
        "fake": bool(latest.get("fake")),
        "questions": [
            {
                k: q.get(k)
                for k in (
                    "id",
                    "p_violation",
                    "violations",
                    "k_valid",
                    "evidence",
                    "notes",
                    "answers",
                )
            }
            for q in latest.get("questions", [])
        ],
    }
    reviews = (
        [
            r
            for r in gate_log.records(root, plan_id)
            if r["kind"] == "review" and r.get("status") == "ok" and r.get("version") == 2
        ]
        if log_ok
        else []  # a broken log is a veto; nothing in it is evidence
    )
    same = [
        r
        for r in reviews
        if r.get("diff_hash") == diff_hash and r.get("critic_hash") == latest.get("critic_hash")
    ]
    if status["fresh"] and status["status"] == "ok" and len(same) > 1:
        pooled: dict[str, dict[str, Any]] = {}
        for r in same:
            for q in r.get("questions", []):
                acc = pooled.setdefault(
                    q["id"],
                    {"id": q["id"], "violations": 0, "k_valid": 0, "evidence": [], "notes": []},
                )
                acc["violations"] += q.get("violations") or 0
                acc["k_valid"] += q.get("k_valid") or 0
                acc["evidence"] += [e for e in q.get("evidence") or [] if e not in acc["evidence"]]
                acc["notes"] += q.get("notes") or []
                acc.setdefault("answers", []).extend(q.get("answers") or [])
        for acc in pooled.values():
            acc["p_violation"] = (
                round(acc["violations"] / acc["k_valid"], 4) if acc["k_valid"] else None
            )
            acc["evidence"], acc["notes"] = acc["evidence"][:10], acc["notes"][:3]
        latest_ids = [q["id"] for q in status["questions"]]
        status["questions"] = [pooled[i] for i in latest_ids if i in pooled]
        status["runs_pooled"] = len(same)
        status["samples_ok"] = sum(_samples_ok(r) for r in same)
        status["fake"] = any(r.get("fake") for r in same)
        status["cross_family_present"] = any(r.get("cross_family_present") for r in same)

    # prior uncertainty: earlier diffs on which a question sat in the uncertain band
    prior: dict[str, int] = {}
    if profile is not None:
        seen: dict[str, set[str]] = {}
        for r in reviews:
            if r.get("diff_hash") == diff_hash:
                continue
            for q in r.get("questions", []):
                p = q.get("p_violation")
                block_t, unsure_t = profile.threshold(q["id"])
                if p is not None and unsure_t <= p < block_t:
                    seen.setdefault(q["id"], set()).add(r["diff_hash"])
        prior = {qid: len(hashes) for qid, hashes in seen.items()}
    return status, prior


def calibration(
    root: Path, profile: judge.Profile | None, critic_hash: str | None
) -> dict[str, Any]:
    if profile is None:
        return {"report": "", "calibrated": []}
    cal = profile.raw.get("calibration", {})
    report = cal.get("report") or ""
    out: dict[str, Any] = {"report": report, "calibrated": [], "critic_hash_match": False}
    if not report or not (root / report).exists():
        return out
    data = json.loads((root / report).read_text(encoding="utf-8"))
    target = float(cal.get("miss_rate_target", 0.10))
    out["critic_hash_match"] = data.get("critic_hash") == critic_hash
    if out["critic_hash_match"]:
        out["calibrated"] = sorted(
            qid
            for qid, m in data.get("questions", {}).items()
            if m.get("miss_rate_upper") is not None and float(m["miss_rate_upper"]) <= target
        )
    return out


def collect(
    root: Path, plan_id: str, plan_text: str, base: str, profile: judge.Profile | None, raw: dict
) -> dict[str, Any]:
    meta = plan_meta(plan_text)
    changed = gitutil.changed(base)
    paths = [c.path for c in changed]
    diff_hash = gitutil.diff_hash(base)
    checks: list[dict[str, Any]] = [
        {
            "name": "plan status in-progress",
            "kind": "hygiene",
            "ok": meta["status_in_progress"],
            "tail": ""
            if meta["status_in_progress"]
            else (
                "Plan frontmatter must say 'status: in-progress' while work is ongoing"
                f" (docs/plans/{plan_id}.md)."
            ),
        },
        {
            "name": "implementation notes filled",
            "kind": "hygiene",
            "ok": meta["notes_filled"],
            "tail": ""
            if meta["notes_filled"]
            else (
                f"Fill in '## Implementation notes' in docs/plans/{plan_id}.md with"
                " decisions and resolved open questions (rule 7)."
            ),
        },
    ]
    checks.extend(
        run_check(f"criterion: {cmd}", "criterion", cmd, CHECK_TAIL)[0] for cmd in meta["criteria"]
    )
    e2e = any(p.startswith("src/kaleta/views/") for p in paths)
    vcmd = "./scripts/verify.sh" + (" --e2e" if e2e else "")
    vcheck, vtext = run_check(vcmd.removeprefix("./scripts/"), "verify", vcmd, VERIFY_TAIL)
    write_state("verify-last.log", vtext + "\n")
    checks.append(vcheck)
    green, secrets = pattern_hits(base, raw)
    log_errors = gate_log.verify(root, plan_id)
    critic, prior = critic_evidence(root, plan_id, diff_hash, profile, log_ok=not log_errors)
    return {
        "plan_id": plan_id,
        "plan": {k: meta[k] for k in ("harness", "title", "manual_criteria")}
        | {"exec_criteria": len(meta["criteria"])},
        "changed": [c.as_dict() for c in changed],
        "diff_hash": diff_hash,
        "maintainer": os.environ.get("KALETA_HARNESS_MAINTAINER") == "1",
        # the hook's environment, which the implementer cannot set (like maintainer mode)
        "test_mode": os.environ.get("KALETA_HARNESS_TEST") == "1",
        "protected_touched": protected_in_diff(paths, root, base),
        "green_washing": green,
        "secret_hits": secrets,
        "run_log_errors": log_errors[:5],
        "checks": checks,
        "critic": critic,
        "prior_uncertain": prior,
        "calibration": calibration(root, profile, critic.get("critic_hash")),
    }


# ── answer ───────────────────────────────────────────────────────────────
def block_json(attempt: int, max_attempts: int, decision: judge.Decision) -> str:
    text = (
        f"DoD gate — attempt {attempt}/{max_attempts} — NOT done yet."
        " Fix everything below, then finish your turn again.\n\n"
    )
    text += "".join(f"- {r['message']}\n\n" for r in decision.reasons)
    if decision.warnings:
        text += "Warnings (not blocking, but address or justify):\n"
        text += "".join(f"- {w}\n" for w in decision.warnings)
    text += RULES_FOOTER
    return json.dumps({"decision": "block", "reason": text})


def main() -> int:
    sys.stdin.read()  # hook payload (unused beyond presence)
    root = gitutil.toplevel()
    os.chdir(root)
    dry = os.environ.get("DOD_GATE_DRY") == "1"

    plan_id = read_state("active-plan")
    if not plan_id:
        return 0
    plan = Path("docs/plans") / f"{plan_id}.md"

    # Auto-disarm: the plan got archived, or the work is DONE and we are no
    # longer on its branch (a forgotten `plan_goal.sh finish` must not judge
    # other sessions).
    branch = gitutil.branch()
    result = read_state("result")
    if (Path("docs/plans/archive") / f"{plan_id}.md").exists() or (
        result == "done" and branch != f"plan/{plan_id}"
    ):
        (STATE / "active-plan").unlink(missing_ok=True)
        print(f"dod-gate: plan {plan_id} is archived/finished — gate disarmed", file=sys.stderr)
        return 0

    # Terminal states stay quiet until `plan_goal.sh start` re-arms the plan.
    if result == "blocked" or (result in ("exhausted", "escalated") and not dry):
        return 0
    if not plan.exists():
        print(f"dod-gate: plan {plan} missing, gate disabled", file=sys.stderr)
        return 0

    max_attempts = int(read_state("max-attempts") or DEFAULT_MAX)
    attempt = int(read_state("attempts") or 0) + 1
    if not dry:
        write_state("attempts", str(attempt))

    base = gitutil.merge_base("main")
    maintainer = os.environ.get("KALETA_HARNESS_MAINTAINER") == "1"
    profile_source = "worktree" if maintainer else "base"
    profile: judge.Profile | None
    profile_error = ""
    try:
        profile = judge.load_profile(root, base=None if maintainer else base)
        raw = profile.raw
    except judge.ProfileError as exc:
        profile, raw, profile_error = None, {}, str(exc)

    inputs = collect(root, plan_id, plan.read_text(encoding="utf-8"), base, profile, raw)
    decision = (
        judge.decide(inputs, profile) if profile else judge.profile_error_decision(profile_error)
    )

    outcome = decision.outcome
    if outcome == "block" and not dry and attempt >= max_attempts:
        outcome = "exhausted"
    note = judge.render_note(decision, inputs, raw.get("meta", {}))
    write_state("decision.md", note)
    record: dict[str, Any] = {
        "dry": dry,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "branch": branch,
        "base": base,
        "diff_hash": inputs["diff_hash"],
        "plan_sha": gitutil.file_sha(plan),
        "checklist_sha": gitutil.file_sha(Path("docs/review-checklist.md")),
        "protected_sha": gitutil.file_sha(Path("docs/harness/protected-paths.txt")),
        "profile": profile.raw if profile else None,
        "profile_source": profile_source,
        "inputs": inputs,
        "decision": decision.as_dict(),
        "outcome": outcome,
    }
    if profile_error:
        record["profile_error"] = profile_error
    gate_log.append(root, plan_id, "gate", record)

    if dry and outcome != "block":
        # plan_goal.sh check: report, change nothing
        if outcome == "done":
            print(f"dod-gate: would be DONE in mode {decision.mode}", file=sys.stderr)
            return 0
        reasons = "\n".join(f"- {r['message']}" for r in decision.reasons)
        print(
            json.dumps({"decision": "block", "reason": f"Would ESCALATE to the owner:\n{reasons}"})
        )
        return 0

    if outcome == "done":
        write_state("result", "done")
        write_state("mode", decision.mode or "")
        manual = inputs["plan"]["manual_criteria"]
        print(
            f"dod-gate: DONE for plan {plan_id} — mode {decision.mode}"
            f" ({decision.risk_class} risk);"
            f" manual criteria left for the owner: {manual}. See .claude/state/decision.md",
            file=sys.stderr,
        )
        for w in decision.warnings:
            print(f"warning: {w}", file=sys.stderr)
        return 0
    if outcome == "escalate":
        write_state("result", "escalated")
        write_state("mode", decision.mode or "")
        write_state("escalated-reason", "\n".join(r["message"] for r in decision.reasons) + "\n")
        print(
            f"dod-gate: ESCALATED to the owner (mode {decision.mode}). The gate will not decide"
            " this; stop and report. See .claude/state/decision.md",
            file=sys.stderr,
        )
        for r in decision.reasons:
            print(f"- {r['message']}", file=sys.stderr)
        return 0
    if outcome == "exhausted":
        write_state("result", "exhausted")
        print(
            f"dod-gate: {attempt}/{max_attempts} attempts exhausted — letting the session stop."
            " Open failures:",
            file=sys.stderr,
        )
        for r in decision.reasons:
            print(f"- {r['message']}", file=sys.stderr)
        return 0
    print(block_json(attempt, max_attempts, decision))
    return 0


def crashed(exc: BaseException) -> int:
    """The gate itself failed: never "done", never a block loop — the owner decides.

    A block would repeat on every Stop without counting toward max-attempts,
    so the run would spin until --max-turns. Escalating ends it with the cause.
    """
    frames = traceback.format_exc().strip().splitlines()[-8:]
    msg = (
        f"DoD gate crashed: {exc!r}. The harness is broken or was fed something it cannot"
        " read; the gate will not decide this run.\n" + "\n".join(frames)
    )
    if os.environ.get("DOD_GATE_DRY") == "1":
        print(json.dumps({"decision": "block", "reason": msg}))
        return 0
    try:
        write_state("result", "escalated")
        write_state("mode", "D")
        write_state("escalated-reason", msg + "\n")
        write_state("gate-crash.log", traceback.format_exc())
    except OSError:
        pass
    print(f"dod-gate: ESCALATED — {msg}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # the judge must never fail open silently
        sys.exit(crashed(exc))
