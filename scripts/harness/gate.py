#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The DoD gate behind the Stop hook ``.claude/hooks/dod-gate.sh`` (ADR-39).

Active only while ``.claude/state/active-plan`` exists. Collects the evidence
for the armed plan, decides, writes a ``gate`` record to the run log
(``gate_log.py``) and answers Claude Code: nothing on stdout lets the session
stop; ``{"decision": "block", "reason": ...}`` makes it keep working.

``DOD_GATE_DRY=1`` (``scripts/plan_goal.sh check``) judges without counting an
attempt; the record is marked ``dry``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # the gate must not leave files in the protected harness dir
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_log  # noqa: E402
import gitutil  # noqa: E402
from protected import protected_in_diff  # noqa: E402

STATE = Path(".claude/state")
DEFAULT_MAX = 6
CHECK_TAIL = 15
TRANSITIONAL_BLOCK = 0.66  # 2 of 3 samples (0.667); replaced by profile thresholds (plan 4)
VERIFY_TAIL = 40

GREEN_WASHING = [
    # id, pattern, applies to, outcome, message
    (
        "skip-xfail",
        r"pytest\.mark\.(skip|xfail)|pytest\.skip\(|@unittest\.skip",
        "added",
        "block",
        "New skip/xfail in the diff — forbidden (rule 4). Fix the root cause instead.",
    ),
    (
        "ignore-imports",
        r"^\s*ignore_imports",
        "added",
        "block",
        "New ignore_imports entry — forbidden (rule 6). The import-linter contract is law.",
    ),
    (
        "type-ignore",
        r"#\s*type:\s*ignore",
        "added",
        "warn",
        (
            "New '# type: ignore' in the diff — justify it in Implementation notes"
            " or remove (rule 10)."
        ),
    ),
    (
        "removed-assert",
        r"^\s*assert",
        "removed-tests",
        "warn",
        (
            "Assertions were removed from existing tests — explain this in"
            " Implementation notes (rule 4)."
        ),
    ),
]

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


# ── plan ─────────────────────────────────────────────────────────────────
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


# ── checks ───────────────────────────────────────────────────────────────
def run_check(name: str, kind: str, cmd: str, tail: int) -> dict[str, Any]:
    t0 = time.monotonic()
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, check=False)
    text = (out.stdout + out.stderr).rstrip()
    return {
        "name": name,
        "kind": kind,
        "cmd": cmd,
        "ok": out.returncode == 0,
        "seconds": round(time.monotonic() - t0, 2),
        "tail": "\n".join(text.splitlines()[-tail:]) if out.returncode else "",
        "_full": text,
    }


def green_washing(base: str) -> list[dict[str, Any]]:
    added, removed = gitutil.diff_lines(base)
    added_code = [d for d in added if d.path and not d.path.startswith("docs/")]
    removed_tests = [d for d in removed if d.path.startswith("tests/")]
    hits = []
    for gid, pattern, scope, outcome, message in GREEN_WASHING:
        rx = re.compile(pattern)
        pool = added_code if scope == "added" else removed_tests
        found = [f"{d.path}:{d.new_line or '-'}" for d in pool if rx.search(d.text)]
        if found:
            hits.append({"id": gid, "outcome": outcome, "message": message, "where": found[:10]})
    return hits


def critic_status(diff_hash: str) -> dict[str, Any]:
    """What the critic (scripts/review_gate.sh -> critic.py) said about this diff."""
    path = STATE / "critic.json"
    if not path.exists():
        return {"present": False}
    try:
        c = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "present": True,
            "fresh": False,
            "status": "error",
            "error": "critic.json unreadable",
        }
    return {
        "present": True,
        "fresh": c.get("diff_hash") == diff_hash,
        "status": c.get("status"),
        "error_kind": c.get("error_kind", ""),
        "error": c.get("error", ""),
        "critic_hash": c.get("critic_hash"),
        "risk_class": c.get("risk_class"),
        "cross_family_present": bool(c.get("cross_family_present")),
        "questions": [
            {
                k: q.get(k)
                for k in ("id", "p_violation", "violations", "k_valid", "evidence", "notes")
            }
            for q in c.get("questions", [])
        ],
    }


# ── collect ──────────────────────────────────────────────────────────────
def collect(root: Path, plan_id: str, plan_text: str, base: str) -> dict[str, Any]:
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
    for cmd in meta["criteria"]:
        c = run_check(f"criterion: {cmd}", "criterion", cmd, CHECK_TAIL)
        c.pop("_full")
        checks.append(c)
    e2e = any(p.startswith("src/kaleta/views/") for p in paths)
    v = run_check(
        "verify.sh" + (" --e2e" if e2e else ""),
        "verify",
        "./scripts/verify.sh" + (" --e2e" if e2e else ""),
        VERIFY_TAIL,
    )
    write_state("verify-last.log", v.pop("_full") + "\n")
    checks.append(v)
    return {
        "plan_id": plan_id,
        "plan": {k: meta[k] for k in ("harness", "title", "manual_criteria")}
        | {"exec_criteria": len(meta["criteria"])},
        "changed": [c.as_dict() for c in changed],
        "diff_hash": diff_hash,
        "maintainer": os.environ.get("KALETA_HARNESS_MAINTAINER") == "1",
        "protected_touched": protected_in_diff(paths, root, base),
        "green_washing": green_washing(base),
        "checks": checks,
        "critic": critic_status(diff_hash),
    }


# ── decide ───────────────────────────────────────────────────────────────
def decide(inputs: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []
    if inputs["protected_touched"] and not inputs["maintainer"]:
        reasons.append(
            "Protected paths changed outside maintainer mode (docs/harness/protected-paths.txt): "
            + " ".join(inputs["protected_touched"])
            + ". Revert them — only the maintainer changes the harness."
        )
    for c in inputs["checks"]:
        if c["ok"]:
            continue
        if c["kind"] == "hygiene":
            reasons.append(c["tail"])
        elif c["kind"] == "criterion":
            reasons.append(f"Acceptance criterion failed: `{c['cmd']}`\n{c['tail']}")
        else:
            reasons.append(f"./scripts/{c['cmd'].removeprefix('./scripts/')} failed:\n{c['tail']}")
    for g in inputs["green_washing"]:
        (reasons if g["outcome"] == "block" else warnings).append(
            f"{g['message']} ({', '.join(g['where'])})"
        )
    if inputs["plan"]["exec_criteria"] == 0:
        warnings.append(
            "Plan has no executable acceptance criteria (backtick commands) — "
            "the gate relies on verify.sh and the reviewer only."
        )
    # Transitional rule until judge-profile-and-autonomy: block on a majority.
    c = inputs["critic"]
    if not c["present"]:
        reasons.append(
            "No critic run yet. Run ./scripts/review_gate.sh (independent critic)"
            " and fix what it finds."
        )
    elif not c["fresh"]:
        reasons.append(
            "Critic run is stale — the diff changed since. Run ./scripts/review_gate.sh again."
        )
    elif c["status"] != "ok":
        reasons.append(f"Critic could not run: {c.get('error') or c['status']}.")
    else:
        for q in c["questions"]:
            p = q["p_violation"]
            ev = ", ".join(f"{e['file']}:{e['line']}" for e in q["evidence"]) or "-"
            notes = " / ".join(q["notes"])
            line = f"{q['id']} p={p} ({q['violations']}/{q['k_valid']}) at {ev}" + (
                f" — {notes}" if notes else ""
            )
            if p is None:
                warnings.append(f"{q['id']}: no valid critic answer (evidence missing or invalid).")
            elif p >= TRANSITIONAL_BLOCK:
                reasons.append(f"Critic found a problem: {line}")
            elif p > 0:
                warnings.append(f"Critic is unsure: {line}")
    return {"outcome": "block" if reasons else "done", "reasons": reasons, "warnings": warnings}


# ── main ─────────────────────────────────────────────────────────────────
def block_json(attempt: int, max_attempts: int, decision: dict[str, Any]) -> str:
    text = (
        f"DoD gate — attempt {attempt}/{max_attempts} — NOT done yet."
        " Fix everything below, then finish your turn again.\n\n"
    )
    text += "".join(f"- {r}\n\n" for r in decision["reasons"])
    if decision["warnings"]:
        text += "Warnings (not blocking, but address or justify):\n"
        text += "".join(f"- {w}\n" for w in decision["warnings"])
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
    inputs = collect(root, plan_id, plan.read_text(encoding="utf-8"), base)
    decision = decide(inputs)

    outcome = decision["outcome"]
    if outcome == "block" and not dry and attempt >= max_attempts:
        outcome = "exhausted"
    gate_log.append(
        root,
        plan_id,
        "gate",
        {
            "dry": dry,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "branch": branch,
            "base": base,
            "diff_hash": inputs["diff_hash"],
            "plan_sha": gitutil.file_sha(plan),
            "checklist_sha": gitutil.file_sha(Path("docs/review-checklist.md")),
            "protected_sha": gitutil.file_sha(Path("docs/harness/protected-paths.txt")),
            "inputs": inputs,
            "decision": decision,
            "outcome": outcome,
        },
    )

    if outcome == "done":
        write_state("result", "done")
        manual = inputs["plan"]["manual_criteria"]
        msg = f"dod-gate: DONE for plan {plan_id} (manual criteria left for the owner: {manual})"
        print(msg, file=sys.stderr)
        for w in decision["warnings"]:
            print(f"warning: {w}", file=sys.stderr)
        return 0
    if outcome == "exhausted":
        write_state("result", "exhausted")
        print(
            f"dod-gate: {attempt}/{max_attempts} attempts exhausted — letting the session stop."
            " Open failures:",
            file=sys.stderr,
        )
        for r in decision["reasons"]:
            print(f"- {r}", file=sys.stderr)
        return 0
    print(block_json(attempt, max_attempts, decision))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # the judge must never fail open silently
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": f"DoD gate crashed: {exc!r}."
                    " Tell the maintainer; do not work around it.",
                }
            )
        )
        sys.exit(0)
